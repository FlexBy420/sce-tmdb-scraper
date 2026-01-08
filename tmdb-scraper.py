import aiohttp
import asyncio
import hashlib
import hmac
import logging
import os
import sys
import json
import xml.etree.ElementTree as ET
from itertools import product

os.makedirs("log", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("log/log.txt", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

FOUND_JSON = "log/tmdb.json"
if not os.path.exists(FOUND_JSON):
    with open(FOUND_JSON, "w", encoding="utf-8") as f:
        json.dump({}, f, indent=4, ensure_ascii=False)

DOMAIN = "http://tmdb.np.dl.playstation.net/"
SECRET_KEY = bytes.fromhex("F5DE66D2680E255B2DF79E74F890EBF349262F618BCAE2A9ACCDEE5156CE8DF2CDF2D48C71173CDC2594465B87405D197CF1AED3B7E9671EEB56CA6753C2E6B0")
MAX_CONCURRENT_REQUESTS = 2000
MAX_RETRIES = 3

def generate_hash(title_id: str) -> str:
    return hmac.new(SECRET_KEY, f"{title_id.upper()}_00".encode(), hashlib.sha1).hexdigest().upper()

def extract_title_from_xml(data: bytes):
    try:
        root = ET.fromstring(data)
        name = root.findtext("name")
        return [name] if name else None
    except Exception:
        return None

def extract_title_from_json(data: bytes):
    try:
        parsed = json.loads(data)
        names = parsed.get("names")
        if not names:
            return None
        return list({n.get("name") for n in names if "name" in n})
    except Exception:
        return None

def sort_title_ids(data: dict) -> dict:
    def sort_key(tid: str):
        prefix = "".join(c for c in tid if c.isalpha())
        number = "".join(c for c in tid if c.isdigit())
        return (prefix, int(number) if number else 0)
    return dict(sorted(data.items(), key=lambda item: sort_key(item[0])))

async def fetch_tmdb(session, semaphore, title_id, path, extension, counter_lock, checked_counter, found_counter, results_dict, retry_ids):
    async with semaphore:
        url = f"{DOMAIN}{path}/{title_id}_00_{generate_hash(title_id)}/{title_id}_00.{extension}"
        #logging.info(url)
        try:
            async with session.get(url) as response:
                async with counter_lock:
                    checked_counter[0] += 1
                if response.status == 404:
                    async with counter_lock:
                        sys.stdout.write(f"\rChecked IDs: {checked_counter[0]} | Found IDs: {found_counter[0]}")
                        sys.stdout.flush()
                    return
                elif response.status != 200:
                    async with counter_lock:
                        retry_ids.append(title_id)
                        sys.stdout.write(f"\rChecked IDs: {checked_counter[0]} | Found IDs: {found_counter[0]}")
                        sys.stdout.flush()
                    return
                raw = await response.read()
                if not raw.strip():
                    title = None
                else:
                    title = extract_title_from_xml(raw) if extension == "xml" else extract_title_from_json(raw)

                os.makedirs(extension, exist_ok=True)
                file_path = f"{extension}/{title_id}.{extension}"
                with open(file_path, "wb") as f:
                    f.write(raw)
                results_dict[title_id] = {"title": title, "url": url}

                async with counter_lock:
                    found_counter[0] += 1
                    sys.stdout.write(f"\rChecked IDs: {checked_counter[0]} | Found IDs: {found_counter[0]}")
                    sys.stdout.flush()

        except Exception:
            async with counter_lock:
                retry_ids.append(title_id)
                checked_counter[0] += 1
                sys.stdout.write(f"\rChecked IDs: {checked_counter[0]} | Found IDs: {found_counter[0]}")
                sys.stdout.flush()

def ps3_prefixes():
    ps3_digital = [f"NP{r}{t}" for r, t in product("EHJKU", "ABCDEFGHIJKLMNOPQRSTUVWXYZ")]
    ps3_physical = [
        f"B{rights}{region}{rtype}"
        for rights, region, rtype in product("CL", "AEJKU", "BDMSX")
        if not ((rtype in "MB") and region != "J")
        and not (rtype == "D" and region not in "EU")
    ]
    return ps3_digital + ps3_physical + ["MRTC"]

def ps1_ps2_prefixes():
    return [f"S{rights}{region}{rtype}" for rights, region, rtype in product("CL", "ACEKPUZ", "ADJMNS")]

def ps4_prefixes():
    return ["CUSA"]

def psp_prefixes():
    return [f"U{rights}{region}{rtype}"for rights, region, rtype in product("CL", "AEJKU", "BDMPSTX")]

def psvita_prefixes():
    return [f"PCS{region}" for region in "ABCDEFGH"] # Based on vita3k compat

async def scrape(prefixes, path, ext, brute=True, batch_size=100000):
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    checked_counter = [0]
    found_counter = [0]
    counter_lock = asyncio.Lock()
    results_dict = {}

    async with aiohttp.ClientSession() as session:
        for prefix in prefixes:
            retry_ids = []
            if brute:
                for start in range(0, 100000, batch_size):
                    tasks = [
                        fetch_tmdb(session, semaphore, f"{prefix}{i:05}", path, ext, counter_lock, checked_counter, found_counter, results_dict, retry_ids)
                        for i in range(start, start + batch_size)
                    ]
                    await asyncio.gather(*tasks)

            else:
                retry_ids = []
                await fetch_tmdb(session, semaphore, prefix, path, ext, counter_lock, checked_counter, found_counter, results_dict, retry_ids)
            for attempt in range(1, MAX_RETRIES + 1):
                if not retry_ids:
                    break
                tasks = [
                    fetch_tmdb(session, semaphore, tid, path, ext, counter_lock, checked_counter, found_counter, results_dict, [])
                    for tid in retry_ids
                ]
                retry_ids = []
                await asyncio.gather(*tasks)

    print()
    results_dict = sort_title_ids(results_dict)

    with open(FOUND_JSON, "r", encoding="utf-8") as f:
        existing = json.load(f)
    existing.update(results_dict)
    existing = sort_title_ids(existing)
    with open(FOUND_JSON, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=4, ensure_ascii=False)
    logging.info(f"Saved {len(results_dict)} IDs from prefixes [{', '.join(prefixes)}]")

def menu():
    print("""
1. All Platforms
2. Only PS3
3. Only PS4
4. Only PS1 / PS2
5. Specific ID (i.e. CUSA12345)
""")
    return input("Choose Option: ").strip()

async def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--all":
        await scrape(ps1_ps2_prefixes() + ps3_prefixes(), "tmdb", "xml")
        await scrape(ps4_prefixes(), "tmdb2", "json")
        return

    while True:
        choice = menu()

        if choice == "1":
            await scrape(ps1_ps2_prefixes() + ps3_prefixes(), "tmdb", "xml")
            await scrape(ps4_prefixes(), "tmdb2", "json")
        elif choice == "2":
            await scrape(ps3_prefixes(), "tmdb", "xml")
        elif choice == "3":
            await scrape(ps4_prefixes(), "tmdb2", "json")
        elif choice == "4":
            await scrape(ps1_ps2_prefixes(), "tmdb", "xml")
        #elif choice == "5":
        #    await scrape(psp_prefixes(), "tmdb", "xml") # only ULJM05170, ULJM05277, ULJM05353 all empty
        #elif choice == "6":
        #    await scrape(psvita_prefixes(), "tmdb", "xml") # 0 json, only empty PCSF00178.xml came up lol
        elif choice == "5":
            tid = input("Enter Title ID: ").strip().upper()
            path = "tmdb2" if tid.startswith("CUSA") else "tmdb"
            ext = "json" if tid.startswith("CUSA") else "xml"
            await scrape([tid], path, ext, brute=False)
        else:
            print("Invalid Option")
            continue

        again = input("\nDo you want to do something else? (y/n): ").strip().lower()
        if again not in ("y", "yes"):
            print("Exiting program...")
            break

if __name__ == "__main__":
    asyncio.run(main())
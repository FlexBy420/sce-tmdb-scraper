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
from urllib.parse import urlparse, parse_qs
import time
import re
import random

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

FOUND_DEV_JSON = "log/tmdb_dev.json"
if not os.path.exists(FOUND_DEV_JSON):
    with open(FOUND_DEV_JSON, "w", encoding="utf-8") as f:
        json.dump({}, f, indent=4, ensure_ascii=False)

UPDATES_JSON = "log/updates.json"
if not os.path.exists(UPDATES_JSON):
    with open(UPDATES_JSON, "w", encoding="utf-8") as f:
        json.dump({}, f, indent=4, ensure_ascii=False)

DOMAIN = "http://tmdb.np.dl.playstation.net/"
DEV_DOMAIN = "http://tmdb.e1-np.dl.playstation.net/"
SECRET_KEY = bytes.fromhex("F5DE66D2680E255B2DF79E74F890EBF349262F618BCAE2A9ACCDEE5156CE8DF2CDF2D48C71173CDC2594465B87405D197CF1AED3B7E9671EEB56CA6753C2E6B0")
MAX_CONCURRENT_REQUESTS = 1000 # set this according to your OS limit
MAX_RETRIES = 3
IMAGE_SEMAPHORE = asyncio.Semaphore(100)

UPDATES_ENV = "np"
UPDATES_URL = "https://a0.ww.{env}.dl.playstation.net/tpl/{env}/{title_id}/{title_id}-ver.xml"
UPDATES_DIR = "updates"
UPDATE_FILE_EXTENSIONS = (".xml", ".json", ".hip")
PS4_UPDATES_URL = "http://gs-sec.ww.np.dl.playstation.net/plo/np/{title_id}/{hash}/{title_id}-ver.xml"
PS4_PATCH_HMAC_KEY = bytes.fromhex("AD62E37F905E06BC19593142281C112CEC0E7EC3E97EFDCAEFCDBAAFA6378D84")
VITA_UPDATES_URL = "http://gs-sec.ww.np.dl.playstation.net/pl/np/{title_id}/{hash}/{title_id}-ver.xml"
VITA_PATCH_HMAC_KEY = bytes.fromhex("E5E278AA1EE34082A088279C83F9BBC806821C52F2AB5D2B4ABD995450355114")

TSS_URL = "https://a0.ww.np.dl.playstation.net/tss/np/{npwr}/{npwr}-{suffix}.tss"
TSS_DIR = "tss_data"
TSS_ID_START = 0
TSS_ID_END = 99999
TSS_SUFFIX_START = 0
TSS_SUFFIX_END = 15
TSS_CONCURRENCY = 1000
TSS_REQUEST_TIMEOUT = 15
TSS_RETRY_BACKOFF = 2

TROPHY_AUTH_BASE_URL = "https://ca.account.sony.com/api/authz/v3/oauth"
TROPHY_AUTH_BASIC = "Basic MDk1MTUxNTktNzIzNy00MzcwLTliNDAtMzgwNmU2N2MwODkxOnVjUGprYTV0bnRCMktxc1A="
TROPHY_REDIRECT_URI = "com.scee.psxandroid.scecompcall://redirect"
TROPHY_CLIENT_ID = "09515159-7237-4370-9b40-3806e67c0891"
TROPHY_SCOPE = "psn:mobile.v2.core psn:clientapp"
TROPHY_DOMAIN = "https://m.np.playstation.com/api/trophy/v1"
TROPHY_GRAPHQL_URL = "https://m.np.playstation.com/api/graphql/v1/op"
TROPHY_DIR = "trophies"
TROPHY_META_DIR = f"{TROPHY_DIR}/_meta"
TROPHY_VALID_LOG = "log/trophies_valid.txt"
TROPHY_SCHEMA_VERSION = 6
TROPHY_ID_START = 0
TROPHY_ID_END = 99999
TROPHY_CONCURRENCY = 4
TROPHY_RETRIES = 3
TROPHY_RETRY_BASE_DELAY = 1.5
TROPHY_LANGUAGE_REQUEST_DELAY = 0.12
TROPHY_FORCE_REFRESH = False
TROPHY_INCLUDE_USER_DATA = False
TROPHY_INCLUDE_GAME_HELP = False
TROPHY_SAVE_DUPLICATE_LOCALES = False
TROPHY_FAST_NOT_FOUND = False

TROPHY_LANGUAGES = [
    ("ar", "ar-SA", "Arabic"),
    ("zh-cn", "zh-CN", "Chinese (Simplified)"),
    ("zh-tw", "zh-TW", "Chinese (Traditional)"),
    ("cs", "cs-CZ", "Czech"),
    ("da", "da-DK", "Danish"),
    ("nl", "nl-NL", "Dutch"),
    ("en-gb", "en-GB", "English (UK)"),
    ("en", "en-US", "English (US)"),
    ("fi", "fi-FI", "Finnish"),
    ("fr-ca", "fr-CA", "French (Canada)"),
    ("fr", "fr-FR", "French (France)"),
    ("de", "de-DE", "German"),
    ("el", "el-GR", "Greek"),
    ("hu", "hu-HU", "Hungarian"),
    ("id", "id-ID", "Indonesian"),
    ("it", "it-IT", "Italian"),
    ("jp", "ja-JP", "Japanese"),
    ("ko", "ko-KR", "Korean"),
    ("no", "nb-NO", "Norwegian"),
    ("pl", "pl-PL", "Polish"),
    ("pt-br", "pt-BR", "Portuguese (Brazil)"),
    ("pt", "pt-PT", "Portuguese (Portugal)"),
    ("ro", "ro-RO", "Romanian"),
    ("ru", "ru-RU", "Russian"),
    ("es-latam", "es-MX", "Spanish (LatAm/Mexico)"),
    ("es", "es-ES", "Spanish (Spain)"),
    ("sv", "sv-SE", "Swedish"),
    ("th", "th-TH", "Thai"),
    ("tr", "tr-TR", "Turkish"),
    ("uk", "uk-UA", "Ukrainian"),
    ("vi", "vi-VN", "Vietnamese"),
]

TROPHY_VALID_ENTRIES = None

class TrophyNotFoundError(Exception):
    pass

class TrophyBadRequestError(Exception):
    pass

def raise_fd_limit():
    try:
        import resource
    except ImportError:
        return None
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    wanted = 65536 if hard == resource.RLIM_INFINITY else min(hard, 65536)
    if soft == resource.RLIM_INFINITY or soft < wanted:
        try:
            resource.setrlimit(resource.RLIMIT_NOFILE, (wanted, hard))
            soft = wanted
        except (ValueError, OSError):
            pass
    return soft

FD_LIMIT = raise_fd_limit()
if FD_LIMIT and FD_LIMIT > 0:
    MAX_CONCURRENT_REQUESTS = min(MAX_CONCURRENT_REQUESTS, max(FD_LIMIT - 200, 50))
    TSS_CONCURRENCY = min(TSS_CONCURRENCY, MAX_CONCURRENT_REQUESTS)

save_queue = asyncio.Queue()

def tmdb_dir(extension, dev=False):
    return f"{'tmdb_dev' if dev else 'tmdb'}/{extension}"

async def file_writer_worker():
    while True:
        item = await save_queue.get()
        if item is None:
            save_queue.task_done()
            break
        file_path, raw = item
        try:
            os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)
            with open(file_path, "wb") as f:
                f.write(raw)
        except Exception as e:
            logging.error(f"Error writing file {file_path}: {e}")
        save_queue.task_done()

async def download_image(session, url, game_dir, silent=False):
    if not url: return
    file_name = os.path.basename(urlparse(url).path)
    file_path = os.path.join(game_dir, file_name)

    # Check if image already exists
    if os.path.exists(file_path):
        return

    async with IMAGE_SEMAPHORE:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as response:
                if response.status == 200:
                    content = await response.read()
                    with open(file_path, 'wb') as f:
                        f.write(content)
                    if not silent:
                        logging.info(f"Successfully downloaded: {file_name}")
                else:
                    logging.error(f"HTTP error {response.status} for image: {url}")
        except Exception as e:
            logging.error(f"Error downloading image {url}: {e}")

async def process_images_for_game(session, title_id, extension, progress_dict=None, dev=False):
    file_path = f"{tmdb_dir(extension, dev)}/{title_id}.{extension}"
    
    # Check if file exists and is not empty before processing
    if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
        if progress_dict: progress_dict['current'] += 1
        return

    urls = set()
    try:
        if extension == "xml":
            with open(file_path, 'r', encoding='utf-8') as f:
                content = ''.join(char for char in f.read() if char.isprintable() or char in '\n\r\t')
            if not content.strip():
                if progress_dict: progress_dict['current'] += 1
                return
            root = ET.fromstring(content)
            for tag in ['.//icon', './/backgroundImage', './/otherImage']:
                for el in root.findall(tag):
                    if el.text: urls.add(el.text)
        else: # JSON
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if not data:
                if progress_dict: progress_dict['current'] += 1
                return
            if 'icons' in data:
                for icon in data['icons']: urls.add(icon.get('icon', ''))
            if data.get('backgroundImage'): urls.add(data.get('backgroundImage'))
            if data.get('otherImage'): urls.add(data.get('otherImage'))
            if data.get('pronunciation'): urls.add(data.get('pronunciation'))
            if data.get('bgm'): urls.add(data.get('bgm'))

        urls = {u for u in urls if u}

        if urls:
            game_dir = os.path.join('icons_dev' if dev else 'icons', title_id)
            os.makedirs(game_dir, exist_ok=True)
            is_silent = progress_dict is not None
            tasks = [download_image(session, url, game_dir, silent=is_silent) for url in urls]
            await asyncio.gather(*tasks)

        # Update and print progress
        if progress_dict:
            progress_dict['current'] += 1
            sys.stdout.write(f"\rProgress: {progress_dict['current']} / {progress_dict['total']} games processed")
            sys.stdout.flush()

    except Exception as e:
        logging.error(f"Error processing images for {title_id}: {e}")
        if progress_dict: progress_dict['current'] += 1

async def bulk_download_images(dev=False):
    async with aiohttp.ClientSession() as session:
        game_list = []

        # Scan for existing non-empty files
        xml_dir = tmdb_dir("xml", dev)
        if os.path.exists(xml_dir):
            for f in os.listdir(xml_dir):
                if f.endswith(".xml") and os.path.getsize(os.path.join(xml_dir, f)) > 0:
                    game_list.append((f.replace(".xml", ""), "xml"))

        json_dir = tmdb_dir("json", dev)
        if os.path.exists(json_dir):
            for f in os.listdir(json_dir):
                if f.endswith(".json") and os.path.getsize(os.path.join(json_dir, f)) > 0:
                    game_list.append((f.replace(".json", ""), "json"))

        total_games = len(game_list)
        if total_games == 0:
            print("No valid source files found to download images.")
            return

        print(f"Starting bulk download for {total_games} games...")
        progress_dict = {'current': 0, 'total': total_games}

        # Concurrent processing of games
        tasks = [process_images_for_game(session, tid, ext, progress_dict, dev) for tid, ext in game_list]
        await asyncio.gather(*tasks)
        print("\nBulk download finished.")

def generate_hash(title_id: str) -> str:
    return hmac.new(SECRET_KEY, f"{title_id.upper()}_00".encode(), hashlib.sha1).hexdigest().upper()

def generate_ps4_patch_hash(title_id: str) -> str:
    return hmac.new(PS4_PATCH_HMAC_KEY, f"np_{title_id.upper()}".encode(), hashlib.sha256).hexdigest()

def generate_vita_patch_hash(title_id: str) -> str:
    return hmac.new(VITA_PATCH_HMAC_KEY, f"np_{title_id.upper()}".encode(), hashlib.sha256).hexdigest()

def update_platform(title_id: str) -> str:
    if title_id.startswith("CUSA"):
        return "PS4"
    if title_id.startswith("PCS"):
        return "PSVita"
    return "PS3"

def update_dir(title_id: str, platform=None) -> str:
    return f"{UPDATES_DIR}/{platform or update_platform(title_id)}/{title_id}"

def build_update_url(title_id: str, platform=None) -> str:
    platform = platform or update_platform(title_id)
    if platform == "PS4":
        return PS4_UPDATES_URL.format(title_id=title_id, hash=generate_ps4_patch_hash(title_id))
    if platform == "PSVita":
        return VITA_UPDATES_URL.format(title_id=title_id, hash=generate_vita_patch_hash(title_id))
    return UPDATES_URL.format(env=UPDATES_ENV, title_id=title_id)

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

def extract_versions_from_update(data: bytes):
    try:
        root = ET.fromstring(data)
        versions = []
        for el in root.iter("package"):
            version = el.get("version")
            if version and version not in versions:
                versions.append(version)
        return versions
    except Exception:
        return []

def extract_update_file_urls(data: bytes):
    try:
        root = ET.fromstring(data)
    except Exception:
        return []
    found = []
    for tag in root.iter("tag"):
        tag_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in tag.get("name", ""))
        for el in tag.iter():
            for attr in ("url", "manifest_url"):
                url = el.get(attr)
                if url and urlparse(url).path.lower().endswith(UPDATE_FILE_EXTENSIONS) and all(url != u for u, _ in found):
                    found.append((url, tag_name))
    names = [os.path.basename(urlparse(u).path) for u, _ in found]
    result = []
    for (url, tag_name), name in zip(found, names):
        if names.count(name) > 1:
            name = f"{tag_name}_{name}"
        result.append((url, name))
    return result

def sort_title_ids(data: dict) -> dict:
    def sort_key(tid: str):
        prefix = "".join(c for c in tid if c.isalpha())
        number = "".join(c for c in tid if c.isdigit())
        return (prefix, int(number) if number else 0)
    return dict(sorted(data.items(), key=lambda item: sort_key(item[0])))

def save_results(json_path, results_dict):
    with open(json_path, "r", encoding="utf-8") as f:
        existing = json.load(f)
    existing.update(results_dict)
    existing = sort_title_ids(existing)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=4, ensure_ascii=False)

async def fetch_tmdb(session, semaphore, title_id, path, extension, counter_lock, checked_counter, found_counter, results_dict, retry_ids, dev=False):
    async with semaphore:
        url = f"{DEV_DOMAIN if dev else DOMAIN}{path}/{title_id}_00_{generate_hash(title_id)}/{title_id}_00.{extension}"
        #logging.info(url)
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                async with counter_lock:
                    checked_counter[0] += 1
                if response.status == 404:
                    if checked_counter[0] % 100 == 0:
                        async with counter_lock:
                            sys.stdout.write(f"\rChecked IDs: {checked_counter[0]} / {checked_counter[1]} | Found IDs: {found_counter[0]}")
                            sys.stdout.flush()
                    return
                elif response.status != 200:
                    async with counter_lock:
                        retry_ids.append(title_id)
                        sys.stdout.write(f"\rChecked IDs: {checked_counter[0]} / {checked_counter[1]} | Found IDs: {found_counter[0]}")
                        sys.stdout.flush()
                    return
                raw = await response.read()
                if not raw.strip():
                    title = None
                else:
                    title = extract_title_from_xml(raw) if extension == "xml" else extract_title_from_json(raw)

                save_dir = tmdb_dir(extension, dev)
                os.makedirs(save_dir, exist_ok=True)
                file_path = f"{save_dir}/{title_id}.{extension}"
                await save_queue.put((file_path, raw))
                
                results_dict[title_id] = {"title": title, "url": url}

                async with counter_lock:
                    found_counter[0] += 1
                    sys.stdout.write(f"\rChecked IDs: {checked_counter[0]} / {checked_counter[1]} | Found IDs: {found_counter[0]}")
                    sys.stdout.flush()

        except Exception:
            async with counter_lock:
                retry_ids.append(title_id)
                checked_counter[0] += 1
                sys.stdout.write(f"\rChecked IDs: {checked_counter[0]} / {checked_counter[1]} | Found IDs: {found_counter[0]}")
                sys.stdout.flush()

async def download_update_file(session, url, save_path):
    if os.path.exists(save_path):
        return
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as response:
                if response.status == 200:
                    raw = await response.read()
                    await save_queue.put((save_path, raw))
                    return
                elif response.status == 404:
                    return
        except Exception:
            pass
        if attempt < MAX_RETRIES:
            await asyncio.sleep(attempt)
    logging.error(f"Failed to download update file {url}")

async def fetch_update(session, semaphore, title_id, counter_lock, checked_counter, found_counter, results_dict, retry_ids, platform=None):
    async with semaphore:
        url = build_update_url(title_id, platform)
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                async with counter_lock:
                    checked_counter[0] += 1
                if response.status == 404:
                    if checked_counter[0] % 100 == 0:
                        async with counter_lock:
                            sys.stdout.write(f"\rChecked IDs: {checked_counter[0]} / {checked_counter[1]} | Found updates: {found_counter[0]}")
                            sys.stdout.flush()
                    return
                elif response.status != 200:
                    async with counter_lock:
                        retry_ids.append(title_id)
                        sys.stdout.write(f"\rChecked IDs: {checked_counter[0]} / {checked_counter[1]} | Found updates: {found_counter[0]}")
                        sys.stdout.flush()
                    return
                raw = await response.read()
                if not raw.strip():
                    return

                save_dir = update_dir(title_id, platform)
                await save_queue.put((f"{save_dir}/{title_id}-ver.xml", raw))

                for file_url, file_name in extract_update_file_urls(raw):
                    await download_update_file(session, file_url, f"{save_dir}/{file_name}")

                results_dict[title_id] = {"platform": platform or update_platform(title_id), "versions": extract_versions_from_update(raw), "url": url}

                async with counter_lock:
                    found_counter[0] += 1
                    sys.stdout.write(f"\rChecked IDs: {checked_counter[0]} / {checked_counter[1]} | Found updates: {found_counter[0]}")
                    sys.stdout.flush()

        except Exception:
            async with counter_lock:
                retry_ids.append(title_id)
                checked_counter[0] += 1
                sys.stdout.write(f"\rChecked IDs: {checked_counter[0]} / {checked_counter[1]} | Found updates: {found_counter[0]}")
                sys.stdout.flush()

def get_tmdb_version(psp2=False):
    while True:
        if psp2:
            v_choice = input("Choose TMDB version (1 - xml, 2 - json, 3 - psp2-tmdb): ").strip()
        else:
            v_choice = input("Choose TMDB version (1 - xml, 2 - json): ").strip()
        if v_choice == "1":
            return "tmdb", "xml"
        elif v_choice == "2":
            return "tmdb2", "json"
        elif v_choice == "3" and psp2:
            return "psp2-tmdb", "xml"
        print("Invalid choice. Please enter 1, 2 or 3." if psp2 else "Invalid choice. Please enter 1 or 2.")

def get_tmdb_domain():
    while True:
        d_choice = input("Choose TMDB domain (1 - prod, 2 - dev): ").strip()
        if d_choice == "1":
            return False
        elif d_choice == "2":
            return True
        print("Invalid choice. Please enter 1 or 2.")

def get_update_backend():
    while True:
        b_choice = input("Choose update backend (1 - auto by prefix, 2 - PS3, 3 - PS4, 4 - PS Vita): ").strip()
        if b_choice == "1":
            return None
        elif b_choice == "2":
            return "PS3"
        elif b_choice == "3":
            return "PS4"
        elif b_choice == "4":
            return "PSVita"
        print("Invalid choice. Please enter 1, 2, 3 or 4.")

def ps3_prefixes():
    ps3_digital = [f"NP{r}{t}" for r, t in product("EHIJKUX", "ABCDEFGHIJKLMNOPQRSTUVWXYZ")]
    ps3_physical = [
        f"B{rights}{region}{rtype}"
        for rights, region, rtype in product("CL", "AEJKU", "BDMSTX")
        if not ((rtype in "MB") and region != "J")
        and not (rtype == "D" and region not in "EU")
    ]
    return ps3_digital + ps3_physical + ["MRTC"]

def ps1_ps2_prefixes():
    return [f"S{rights}{region}{rtype}" for rights, region, rtype in product("CL", "ACEKPUZ", "ADJMNS")] + [f"P{letter}PX" for letter in "ABCDET"] + ["SIPS"]

def ps4_prefixes():
    return ["CUSA"]

def ps5_prefixes():
    return ["PPSA"]

def psp_prefixes():
    return [f"U{rights}{region}{rtype}"for rights, region, rtype in product("CL", "AEJKU", "BDMPSTX")]

def psvita_prefixes():
    return [f"PCS{region}" for region in "ABCDEFGH"] # Based on vita3k compat

def dev_prefixes():
    return ["TEST"] + ["NPXS"] + ["NPXX"] + ["NPWR"]

async def scrape(prefixes, path, ext, brute=True, batch_size=100000, dev=False):
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    checked_counter = [0, len(prefixes) * 100000 if brute else len(prefixes)]
    found_counter = [0]
    counter_lock = asyncio.Lock()
    results_dict = {}

    writer_task = asyncio.create_task(file_writer_worker())

    connector = aiohttp.TCPConnector(limit=0, ttl_dns_cache=600, use_dns_cache=True)
    async with aiohttp.ClientSession(connector=connector) as session:
        for prefix in prefixes:
            retry_ids = []
            if brute:
                for start in range(0, 100000, batch_size):
                    tasks = [
                        fetch_tmdb(session, semaphore, f"{prefix}{i:05}", path, ext, counter_lock, checked_counter, found_counter, results_dict, retry_ids, dev)
                        for i in range(start, start + batch_size)
                    ]
                    await asyncio.gather(*tasks)

            else:
                retry_ids = []
                await fetch_tmdb(session, semaphore, prefix, path, ext, counter_lock, checked_counter, found_counter, results_dict, retry_ids, dev)
            for attempt in range(1, MAX_RETRIES + 1):
                if not retry_ids:
                    break
                current_ids = retry_ids
                retry_ids = []
                checked_counter[0] -= len(current_ids)
                sys.stdout.write(f"\rRetrying {len(current_ids)} IDs (attempt {attempt}/{MAX_RETRIES})...")
                sys.stdout.flush()
                tasks = [
                    fetch_tmdb(session, semaphore, tid, path, ext, counter_lock, checked_counter, found_counter, results_dict, retry_ids, dev)
                    for tid in current_ids
                ]
                await asyncio.gather(*tasks)

    await save_queue.join()
    await save_queue.put(None)
    await writer_task

    sys.stdout.write(f"\rChecked IDs: {checked_counter[0]} / {checked_counter[1]} | Found IDs: {found_counter[0]}")
    print()
    results_dict = sort_title_ids(results_dict)

    save_results(FOUND_DEV_JSON if dev else FOUND_JSON, results_dict)
    logging.info(f"Saved {len(results_dict)} IDs from prefixes [{', '.join(prefixes)}]")

async def scrape_updates(prefixes, brute=True, batch_size=100000, platform=None):
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    checked_counter = [0, len(prefixes) * 100000 if brute else len(prefixes)]
    found_counter = [0]
    counter_lock = asyncio.Lock()
    results_dict = {}

    writer_task = asyncio.create_task(file_writer_worker())

    connector = aiohttp.TCPConnector(limit=0, ttl_dns_cache=600, use_dns_cache=True, ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        for prefix in prefixes:
            retry_ids = []
            if brute:
                for start in range(0, 100000, batch_size):
                    tasks = [
                        fetch_update(session, semaphore, f"{prefix}{i:05}", counter_lock, checked_counter, found_counter, results_dict, retry_ids, platform)
                        for i in range(start, start + batch_size)
                    ]
                    await asyncio.gather(*tasks)
            else:
                await fetch_update(session, semaphore, prefix, counter_lock, checked_counter, found_counter, results_dict, retry_ids, platform)
            for attempt in range(1, MAX_RETRIES + 1):
                if not retry_ids:
                    break
                current_ids = retry_ids
                retry_ids = []
                checked_counter[0] -= len(current_ids)
                sys.stdout.write(f"\rRetrying {len(current_ids)} IDs (attempt {attempt}/{MAX_RETRIES})...")
                sys.stdout.flush()
                tasks = [
                    fetch_update(session, semaphore, tid, counter_lock, checked_counter, found_counter, results_dict, retry_ids, platform)
                    for tid in current_ids
                ]
                await asyncio.gather(*tasks)

    await save_queue.join()
    await save_queue.put(None)
    await writer_task

    sys.stdout.write(f"\rChecked IDs: {checked_counter[0]} / {checked_counter[1]} | Found updates: {found_counter[0]}")
    print()
    results_dict = sort_title_ids(results_dict)

    save_results(UPDATES_JSON, results_dict)
    logging.info(f"Saved {len(results_dict)} update files from prefixes [{', '.join(prefixes)}]")

def build_tss_targets():
    for npwr_num in range(TSS_ID_START, TSS_ID_END + 1):
        npwr = f"NPWR{npwr_num:05d}_00"
        for suffix in range(TSS_SUFFIX_START, TSS_SUFFIX_END + 1):
            url = TSS_URL.format(npwr=npwr, suffix=suffix)
            save_path = os.path.join(TSS_DIR, f"{npwr}-{suffix}.tss")
            yield url, save_path

class TssStats:
    def __init__(self, total):
        self.total = total
        self.found = 0
        self.not_found = 0
        self.errors = 0
        self.processed = 0

def print_tss_progress(stats):
    sys.stdout.write(f"\rChecked IDs: {stats.processed} / {stats.total} | Found files: {stats.found}")
    sys.stdout.flush()

async def fetch_tss(session, url, save_path, stats):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            timeout = aiohttp.ClientTimeout(total=TSS_REQUEST_TIMEOUT)
            async with session.get(url, timeout=timeout) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    await save_queue.put((save_path, data))
                    stats.found += 1
                    stats.processed += 1
                    print_tss_progress(stats)
                    return
                elif resp.status != 429 and resp.status < 500:
                    stats.not_found += 1
                    stats.processed += 1
                    return
        except (asyncio.TimeoutError, aiohttp.ClientError):
            pass
        except Exception as e:
            logging.error(f"Unexpected error for {url}: {e}")
            stats.errors += 1
            stats.processed += 1
            return

        if attempt < MAX_RETRIES:
            await asyncio.sleep(TSS_RETRY_BACKOFF * attempt)

    logging.error(f"All {MAX_RETRIES} attempts failed for {url}")
    stats.errors += 1
    stats.processed += 1

async def tss_worker(queue, session, stats):
    while True:
        item = await queue.get()
        if item is None:
            queue.task_done()
            break
        url, save_path = item
        try:
            await fetch_tss(session, url, save_path, stats)
            if stats.processed % 100 == 0:
                print_tss_progress(stats)
        finally:
            queue.task_done()

async def scrape_tss():
    os.makedirs(TSS_DIR, exist_ok=True)

    start_time = time.time()
    total_targets = (TSS_ID_END - TSS_ID_START + 1) * (TSS_SUFFIX_END - TSS_SUFFIX_START + 1)

    queue = asyncio.Queue(maxsize=TSS_CONCURRENCY * 4)
    stats = TssStats(total_targets)

    writer_task = asyncio.create_task(file_writer_worker())

    connector = aiohttp.TCPConnector(limit=TSS_CONCURRENCY, ttl_dns_cache=300, ssl=False)
    headers = {"User-Agent": "Mozilla/5.0"}

    async with aiohttp.ClientSession(connector=connector, headers=headers) as session:
        workers = [
            asyncio.create_task(tss_worker(queue, session, stats))
            for _ in range(TSS_CONCURRENCY)
        ]

        for target in build_tss_targets():
            await queue.put(target)

        for _ in workers:
            await queue.put(None)

        await queue.join()
        await asyncio.gather(*workers)

    await save_queue.join()
    await save_queue.put(None)
    await writer_task

    print()
    elapsed = time.time() - start_time
    logging.info(
        f"Saved {stats.found} TSS files (not found: {stats.not_found}, errors: {stats.errors}) in {elapsed:.1f}s"
    )

def trophy_format_npwr(index):
    return f"NPWR{index:05d}_00"

def trophy_platform_needs_legacy_service(platform):
    if not isinstance(platform, str):
        return False
    return bool(re.search(r"(?:^|,|\s)(PS3|PS4|PSVITA|PS Vita)(?:$|,|\s)", platform, re.IGNORECASE))

def trophy_platform_uses_trophy2(platform):
    if not isinstance(platform, str):
        return False
    return bool(re.search(r"(?:PS5|PSPC|PC)", platform, re.IGNORECASE))

async def trophy_exchange_npsso_for_code(session, npsso):
    url = f"{TROPHY_AUTH_BASE_URL}/authorize"
    params = {
        "access_type": "offline",
        "client_id": TROPHY_CLIENT_ID,
        "scope": TROPHY_SCOPE,
        "redirect_uri": TROPHY_REDIRECT_URI,
        "response_type": "code",
    }
    headers = {"Cookie": f"npsso={npsso}"}
    async with session.get(url, params=params, headers=headers, allow_redirects=False, timeout=aiohttp.ClientTimeout(total=15)) as response:
        location = response.headers.get("Location")
        if not location:
            raise Exception("PSN did not return a redirect; NPSSO may be invalid or expired.")
        parsed = urlparse(location)
        qs = parse_qs(parsed.query)
        code = qs.get("code", [None])[0]
        if not code:
            raise Exception("Could not extract access code from PSN redirect.")
        return code

async def trophy_exchange_code_for_tokens(session, code):
    url = f"{TROPHY_AUTH_BASE_URL}/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded", "Authorization": TROPHY_AUTH_BASIC}
    data = {
        "code": code,
        "redirect_uri": TROPHY_REDIRECT_URI,
        "grant_type": "authorization_code",
        "token_format": "jwt",
    }
    async with session.post(url, headers=headers, data=data, timeout=aiohttp.ClientTimeout(total=15)) as response:
        raw = await response.json(content_type=None)
        if response.status != 200 or "access_token" not in raw:
            raise Exception(f"Failed to exchange access code for tokens: {raw}")
        return raw

async def trophy_exchange_refresh_token(session, refresh_token):
    url = f"{TROPHY_AUTH_BASE_URL}/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded", "Authorization": TROPHY_AUTH_BASIC}
    data = {
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
        "scope": TROPHY_SCOPE,
        "token_format": "jwt",
    }
    async with session.post(url, headers=headers, data=data, timeout=aiohttp.ClientTimeout(total=15)) as response:
        raw = await response.json(content_type=None)
        if response.status != 200 or "access_token" not in raw:
            raise Exception(f"Failed to refresh tokens: {raw}")
        return raw

async def trophy_refresh_tokens(session, auth_state, auth_lock):
    before_version = auth_state["version"]
    async with auth_lock:
        if auth_state["version"] != before_version:
            return
        refresh_token = auth_state.get("refresh_token")
        tokens = None
        if refresh_token:
            try:
                tokens = await trophy_exchange_refresh_token(session, refresh_token)
            except Exception:
                tokens = None
        if tokens is None:
            code = await trophy_exchange_npsso_for_code(session, auth_state["npsso"])
            tokens = await trophy_exchange_code_for_tokens(session, code)
        auth_state["access_token"] = tokens["access_token"]
        if tokens.get("refresh_token"):
            auth_state["refresh_token"] = tokens["refresh_token"]
        auth_state["version"] += 1

async def trophy_api_get(session, auth_state, auth_lock, url, params=None, accept_language=None):
    attempt = 1
    auth_renewals = 0
    while True:
        headers = {"Authorization": f"Bearer {auth_state['access_token']}"}
        if accept_language:
            headers["Accept-Language"] = accept_language
        try:
            async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as response:
                if response.status == 401 and auth_renewals < 2:
                    auth_renewals += 1
                    await trophy_refresh_tokens(session, auth_state, auth_lock)
                    continue
                if response.status == 404:
                    raise TrophyNotFoundError(url)
                if response.status == 400:
                    text = await response.text()
                    raise TrophyBadRequestError(text)
                if response.status != 200:
                    raise Exception(f"HTTP {response.status} for {url}")
                return await response.json(content_type=None)
        except (TrophyNotFoundError, TrophyBadRequestError):
            raise
        except Exception:
            if attempt >= TROPHY_RETRIES:
                raise
            await asyncio.sleep(TROPHY_RETRY_BASE_DELAY * attempt + random.random() * 0.5)
            attempt += 1

async def trophy_get_groups_raw(session, auth_state, auth_lock, npcid, service_name, accept_language):
    url = f"{TROPHY_DOMAIN}/npCommunicationIds/{npcid}/trophyGroups"
    params = {"npServiceName": service_name} if service_name else None
    data = await trophy_api_get(session, auth_state, auth_lock, url, params, accept_language)
    if not isinstance(data, dict) or not data.get("trophyTitleName") or data.get("trophySetVersion") is None or not isinstance(data.get("trophyGroups"), list):
        raise Exception(f"Invalid trophy groups response for {npcid}")
    return data

async def trophy_discover_title(session, auth_state, auth_lock, npcid, accept_language):
    try:
        groups = await trophy_get_groups_raw(session, auth_state, auth_lock, npcid, None, accept_language)
        platform = groups.get("trophyTitlePlatform")
        if trophy_platform_needs_legacy_service(platform):
            groups = await trophy_get_groups_raw(session, auth_state, auth_lock, npcid, "trophy", accept_language)
            return "trophy", groups
        if trophy_platform_uses_trophy2(platform):
            return "trophy2", groups
        return None, groups
    except TrophyNotFoundError:
        if TROPHY_FAST_NOT_FOUND:
            raise
        try:
            groups = await trophy_get_groups_raw(session, auth_state, auth_lock, npcid, "trophy", accept_language)
            return "trophy", groups
        except TrophyNotFoundError:
            raise
        except Exception:
            groups = await trophy_get_groups_raw(session, auth_state, auth_lock, npcid, "trophy2", accept_language)
            return "trophy2", groups
    except TrophyBadRequestError:
        try:
            groups = await trophy_get_groups_raw(session, auth_state, auth_lock, npcid, "trophy", accept_language)
            return "trophy", groups
        except TrophyNotFoundError:
            raise
        except Exception:
            groups = await trophy_get_groups_raw(session, auth_state, auth_lock, npcid, "trophy2", accept_language)
            return "trophy2", groups

async def trophy_fetch_all_trophies(session, auth_state, auth_lock, npcid, service_name, accept_language):
    pages = []
    seen_offsets = set()
    offset = None
    while True:
        url = f"{TROPHY_DOMAIN}/npCommunicationIds/{npcid}/trophyGroups/all/trophies"
        params = {}
        if service_name:
            params["npServiceName"] = service_name
        if offset is not None:
            params["offset"] = offset
        response = await trophy_api_get(session, auth_state, auth_lock, url, params, accept_language)
        if not isinstance(response, dict) or not isinstance(response.get("trophies"), list):
            raise Exception(f"Trophy response does not contain trophies[] for {npcid}")
        pages.append(response)
        trophies = response.get("trophies") or []
        total = response.get("totalItemCount", len(trophies))
        collected = sum(len(p.get("trophies") or []) for p in pages)
        next_offset = response.get("nextOffset")
        if collected >= total or next_offset is None:
            break
        try:
            next_offset = int(next_offset)
        except Exception:
            break
        if next_offset in seen_offsets:
            break
        seen_offsets.add(next_offset)
        offset = next_offset
    if not pages:
        return None
    if len(pages) == 1:
        return pages[0]
    merged = dict(pages[0])
    merged["trophies"] = [t for p in pages for t in (p.get("trophies") or [])]
    merged["_pagination"] = {"pageCount": len(pages)}
    merged.pop("nextOffset", None)
    merged.pop("previousOffset", None)
    return merged

async def trophy_fetch_all_user_trophies(session, auth_state, auth_lock, npcid, service_name):
    pages = []
    seen_offsets = set()
    offset = None
    while True:
        url = f"{TROPHY_DOMAIN}/users/me/npCommunicationIds/{npcid}/trophyGroups/all/trophies"
        params = {}
        if service_name:
            params["npServiceName"] = service_name
        if offset is not None:
            params["offset"] = offset
        response = await trophy_api_get(session, auth_state, auth_lock, url, params)
        pages.append(response)
        trophies = response.get("trophies") or []
        total = response.get("totalItemCount", len(trophies))
        collected = sum(len(p.get("trophies") or []) for p in pages)
        next_offset = response.get("nextOffset")
        if collected >= total or next_offset is None:
            break
        try:
            next_offset = int(next_offset)
        except Exception:
            break
        if next_offset in seen_offsets:
            break
        seen_offsets.add(next_offset)
        offset = next_offset
    if not pages:
        return None
    if len(pages) == 1:
        return pages[0]
    merged = dict(pages[0])
    merged["trophies"] = [t for p in pages for t in (p.get("trophies") or [])]
    merged["_pagination"] = {"pageCount": len(pages)}
    merged.pop("nextOffset", None)
    merged.pop("previousOffset", None)
    return merged

async def trophy_fetch_game_help(session, auth_state, auth_lock, npcid, accept_language):
    availability_hash = "71bf26729f2634f4d8cca32ff73aaf42b3b76ad1d2f63b490a809b66483ea5a7"
    tips_hash = "93768752a9f4ef69922a543e2209d45020784d8781f57b37a5294e6e206c5630"

    async def graphql(operation_name, variables, sha_hash):
        params = {
            "operationName": operation_name,
            "variables": json.dumps(variables),
            "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": sha_hash}}),
        }
        headers = {
            "Authorization": f"Bearer {auth_state['access_token']}",
            "apollographql-client-name": "PlayStationApp-Android",
            "content-type": "application/json",
        }
        if accept_language:
            headers["Accept-Language"] = accept_language
        async with session.get(TROPHY_GRAPHQL_URL, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as response:
            if response.status != 200:
                raise Exception(f"Game Help HTTP {response.status}")
            return await response.json(content_type=None)

    availability = await graphql("metGetHintAvailability", {"npCommId": npcid}, availability_hash)
    available = ((availability.get("data") or {}).get("hintAvailabilityRetrieve") or {}).get("trophies")
    if not isinstance(available, list) or not available:
        return {"availability": availability, "tips": None}

    trophy_args = [
        {"trophyId": str(v["trophyId"]), "udsObjectId": str(v["udsObjectId"]), "helpType": str(v["helpType"])}
        for v in available if v and v.get("trophyId") is not None and v.get("udsObjectId") is not None and v.get("helpType") is not None
    ]
    if not trophy_args:
        return {"availability": availability, "tips": None}

    tips = await graphql("metGetTips", {"npCommId": npcid, "trophies": trophy_args}, tips_hash)
    return {"availability": availability, "tips": tips}

def trophy_json_equal(a, b):
    return a == b

def trophy_merge_api_responses(groups, trophies, npcid, service_name):
    result = {}
    owners = {}
    conflicts = {}

    def add_source(source_name, source):
        if not isinstance(source, dict):
            return
        for key, value in source.items():
            if value is None:
                continue
            if key not in result:
                result[key] = value
                owners[key] = source_name
                continue
            if trophy_json_equal(result[key], value):
                continue
            if key not in conflicts:
                conflicts[key] = {owners.get(key, "firstResponse"): result[key]}
            conflicts[key][source_name] = value
            if source_name == "titleTrophies":
                result[key] = value
                owners[key] = source_name

    add_source("trophyGroups", groups)
    add_source("titleTrophies", trophies)

    if "npCommunicationId" not in result:
        result["npCommunicationId"] = npcid
    if "npServiceName" not in result and service_name:
        result["npServiceName"] = service_name

    if conflicts:
        result["apiFieldConflicts"] = conflicts

    return result

def trophy_merge_user_data(data, user_data):
    if not isinstance(user_data, dict):
        return data

    result = dict(data)
    static_trophies = data.get("trophies") if isinstance(data.get("trophies"), list) else []
    user_trophies = user_data.get("trophies") if isinstance(user_data.get("trophies"), list) else []
    by_id = {str(t.get("trophyId")): t for t in user_trophies}
    matched = set()

    merged_trophies = []
    for trophy in static_trophies:
        tid = str(trophy.get("trophyId"))
        user_trophy = by_id.get(tid)
        if not user_trophy:
            merged_trophies.append(trophy)
            continue
        matched.add(tid)
        extra = {}
        for key, value in user_trophy.items():
            if key == "trophyId" or value is None:
                continue
            if key in trophy and trophy_json_equal(trophy[key], value):
                continue
            extra[key] = value
        merged_trophies.append({**trophy, "user": extra} if extra else trophy)
    result["trophies"] = merged_trophies

    unmatched = [t for t in user_trophies if str(t.get("trophyId")) not in matched]
    if unmatched:
        result["userOnlyTrophies"] = unmatched

    response_extras = {}
    for key, value in user_data.items():
        if key == "trophies" or value is None:
            continue
        if key in result and trophy_json_equal(result[key], value):
            continue
        response_extras[key] = value
    if response_extras:
        result["userTrophyData"] = response_extras

    return result

def trophy_localization_signature(groups, trophies):
    group_list = groups.get("trophyGroups") if isinstance(groups.get("trophyGroups"), list) else []
    trophy_list = trophies.get("trophies") if isinstance(trophies.get("trophies"), list) else []
    localized = {
        "titleName": groups.get("trophyTitleName"),
        "titleDetail": groups.get("trophyTitleDetail"),
        "groups": [{"id": g.get("trophyGroupId"), "name": g.get("trophyGroupName"), "detail": g.get("trophyGroupDetail")} for g in group_list],
        "trophies": [{"id": t.get("trophyId"), "name": t.get("trophyName"), "detail": t.get("trophyDetail"), "rewardName": t.get("trophyRewardName")} for t in trophy_list],
    }
    return hashlib.sha256(json.dumps(localized, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()

def trophy_manifest_path(npcid):
    return os.path.join(TROPHY_META_DIR, f"{npcid}.json")

def trophy_locale_path(folder, npcid):
    return os.path.join(TROPHY_DIR, folder, f"{npcid}.json")

def trophy_read_json(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def trophy_save_json_if_changed(file_path, data):
    os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)
    new_json = json.dumps(data, indent=2, ensure_ascii=False)
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            old_text = f.read()
        if old_text == new_json:
            return False
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(new_json)
    return True

def trophy_get_valid_entries():
    global TROPHY_VALID_ENTRIES
    if TROPHY_VALID_ENTRIES is None:
        entries = set()
        if os.path.exists(TROPHY_VALID_LOG):
            with open(TROPHY_VALID_LOG, "r", encoding="utf-8") as f:
                for line in f:
                    match = re.match(r"^(NPWR\d{5}_\d{2})\b", line)
                    if match:
                        entries.add(match.group(1))
        TROPHY_VALID_ENTRIES = entries
    return TROPHY_VALID_ENTRIES

def trophy_append_valid_log(npcid, title, platform):
    valid_entries = trophy_get_valid_entries()
    if npcid in valid_entries:
        return
    os.makedirs(os.path.dirname(TROPHY_VALID_LOG) or ".", exist_ok=True)
    safe_title = title or "<unknown title>"
    safe_platform = platform or "<unknown platform>"
    with open(TROPHY_VALID_LOG, "a", encoding="utf-8") as f:
        f.write(f"{npcid} - {safe_title} [{safe_platform}]\n")
    valid_entries.add(npcid)

def trophy_remove_valid_log_entry(npcid):
    valid_entries = trophy_get_valid_entries()
    if npcid not in valid_entries or not os.path.exists(TROPHY_VALID_LOG):
        return
    with open(TROPHY_VALID_LOG, "r", encoding="utf-8") as f:
        lines = f.readlines()
    kept = [l for l in lines if not l.startswith(f"{npcid} ") and l.strip() != npcid]
    with open(TROPHY_VALID_LOG, "w", encoding="utf-8") as f:
        f.writelines(kept)
    valid_entries.discard(npcid)

def trophy_is_valid_saved_json(data):
    if not isinstance(data, dict):
        return False
    title = data.get("trophyTitleName") or data.get("title")
    return bool(
        isinstance(data.get("npCommunicationId"), str)
        and isinstance(title, str) and title.strip() != ""
        and isinstance(data.get("trophies"), list) and len(data["trophies"]) > 0
    )

def trophy_remove_invalid_cached_locale(folder, npcid):
    file_path = trophy_locale_path(folder, npcid)
    if not os.path.exists(file_path):
        return False
    existing = trophy_read_json(file_path)
    if trophy_is_valid_saved_json(existing):
        return False
    os.remove(file_path)
    return True

def trophy_remove_stored_if_invalid(npcid):
    removed = False
    for folder, _, _ in TROPHY_LANGUAGES:
        removed = trophy_remove_invalid_cached_locale(folder, npcid) or removed

    meta = trophy_manifest_path(npcid)
    if os.path.exists(meta):
        manifest = trophy_read_json(meta) or {}
        successful_count = manifest.get("successfulLocaleCount", 0)
        has_valid_locale = any(
            os.path.exists(trophy_locale_path(folder, npcid)) and trophy_is_valid_saved_json(trophy_read_json(trophy_locale_path(folder, npcid)))
            for folder, _, _ in TROPHY_LANGUAGES
        )
        if successful_count <= 0 or not has_valid_locale:
            os.remove(meta)
            removed = True

    return removed

def trophy_can_skip_whole_title(npcid, remote_version, languages):
    if TROPHY_FORCE_REFRESH:
        return False
    manifest = trophy_read_json(trophy_manifest_path(npcid))
    if not manifest or manifest.get("schemaVersion") != TROPHY_SCHEMA_VERSION:
        return False
    if str(manifest.get("trophySetVersion") or "") != str(remote_version or ""):
        return False

    requested_headers = sorted(h for _, h, _ in languages)
    previous_headers = sorted(v.get("acceptLanguage") for v in (manifest.get("requestedLanguages") or []))
    if requested_headers != previous_headers:
        return False
    if bool(manifest.get("includeUserData")) != bool(TROPHY_INCLUDE_USER_DATA):
        return False
    if bool(manifest.get("includeGameHelp")) != bool(TROPHY_INCLUDE_GAME_HELP):
        return False
    if bool(manifest.get("saveDuplicateLocales")) != bool(TROPHY_SAVE_DUPLICATE_LOCALES):
        return False

    for locale in manifest.get("locales") or []:
        if locale.get("error") or locale.get("gameHelpError"):
            return False
        if locale.get("saved") is False:
            continue
        if not os.path.exists(trophy_locale_path(locale.get("folder"), npcid)):
            return False

    return True

async def trophy_scrape_id(session, auth_state, auth_lock, npcid, languages, counter_lock, checked_counter, found_counter):
    primary = next((l for l in languages if l[0] == "en"), languages[0])

    try:
        service_name, groups = await trophy_discover_title(session, auth_state, auth_lock, npcid, primary[1])
    except TrophyNotFoundError:
        trophy_remove_stored_if_invalid(npcid)
        trophy_remove_valid_log_entry(npcid)
        async with counter_lock:
            checked_counter[0] += 1
            sys.stdout.write(f"\rChecked IDs: {checked_counter[0]} / {checked_counter[1]} | Found trophies: {found_counter[0]}")
            sys.stdout.flush()
        return
    except Exception as e:
        logging.error(f"Trophy discovery failed for {npcid}: {e}")
        async with counter_lock:
            checked_counter[0] += 1
            sys.stdout.write(f"\rChecked IDs: {checked_counter[0]} / {checked_counter[1]} | Found trophies: {found_counter[0]}")
            sys.stdout.flush()
        return

    remote_version = groups.get("trophySetVersion")
    title = groups.get("trophyTitleName") or "<unknown title>"
    platform = groups.get("trophyTitlePlatform") or "<unknown platform>"

    if trophy_can_skip_whole_title(npcid, remote_version, languages):
        trophy_append_valid_log(npcid, title, platform)
        async with counter_lock:
            checked_counter[0] += 1
            found_counter[0] += 1
            sys.stdout.write(f"\rChecked IDs: {checked_counter[0]} / {checked_counter[1]} | Found trophies: {found_counter[0]}")
            sys.stdout.flush()
        return

    user_data = None
    user_data_error = None
    if TROPHY_INCLUDE_USER_DATA:
        try:
            user_data = await trophy_fetch_all_user_trophies(session, auth_state, auth_lock, npcid, service_name)
        except Exception as e:
            user_data_error = str(e)

    locales = []
    signature_owners = {}
    ordered_languages = [primary] + [l for l in languages if l[1] != primary[1]]

    for folder, header, label in ordered_languages:
        try:
            if header == primary[1]:
                groups_for_lang = groups
            else:
                groups_for_lang = await trophy_get_groups_raw(session, auth_state, auth_lock, npcid, service_name, header)

            trophies = await trophy_fetch_all_trophies(session, auth_state, auth_lock, npcid, service_name, header)
            if not trophies or not trophies.get("trophies"):
                trophy_remove_invalid_cached_locale(folder, npcid)
                raise Exception("Trophy list is empty; nothing will be saved for this locale.")

            game_help = None
            game_help_error = None
            if TROPHY_INCLUDE_GAME_HELP and trophy_platform_uses_trophy2(groups_for_lang.get("trophyTitlePlatform") or platform):
                try:
                    game_help = await trophy_fetch_game_help(session, auth_state, auth_lock, npcid, header)
                except Exception as e:
                    game_help_error = str(e)

            signature = trophy_localization_signature(groups_for_lang, trophies)
            same_content_as = signature_owners.get(signature)
            if not same_content_as:
                signature_owners[signature] = folder

            data = trophy_merge_api_responses(groups_for_lang, trophies, npcid, service_name)
            if TROPHY_INCLUDE_USER_DATA and user_data:
                data = trophy_merge_user_data(data, user_data)
            if TROPHY_INCLUDE_GAME_HELP and game_help:
                data["gameHelp"] = game_help

            should_save = TROPHY_SAVE_DUPLICATE_LOCALES or not same_content_as
            file_path = trophy_locale_path(folder, npcid)
            if should_save:
                trophy_save_json_if_changed(file_path, data)
            elif os.path.exists(file_path):
                os.remove(file_path)

            locales.append({
                "folder": folder,
                "acceptLanguage": header,
                "label": label,
                "signature": signature,
                "sameContentAs": same_content_as,
                "gameHelpError": game_help_error,
                "saved": should_save,
                "file": os.path.relpath(file_path, TROPHY_DIR).replace("\\", "/") if should_save else None,
            })

            if TROPHY_LANGUAGE_REQUEST_DELAY > 0:
                await asyncio.sleep(TROPHY_LANGUAGE_REQUEST_DELAY)
        except Exception as e:
            locales.append({
                "folder": folder,
                "acceptLanguage": header,
                "label": label,
                "error": str(e),
                "saved": False,
            })

    successful = [l for l in locales if not l.get("error")]

    if not successful:
        trophy_remove_stored_if_invalid(npcid)
        async with counter_lock:
            checked_counter[0] += 1
            sys.stdout.write(f"\rChecked IDs: {checked_counter[0]} / {checked_counter[1]} | Found trophies: {found_counter[0]}")
            sys.stdout.flush()
        return

    unique_signatures = {l["signature"] for l in successful}

    manifest = {
        "schemaVersion": TROPHY_SCHEMA_VERSION,
        "npCommunicationId": npcid,
        "trophySetVersion": remote_version,
        "trophyTitleName": groups.get("trophyTitleName"),
        "trophyTitleDetail": groups.get("trophyTitleDetail"),
        "trophyTitleIconUrl": groups.get("trophyTitleIconUrl"),
        "trophyTitlePlatform": groups.get("trophyTitlePlatform"),
        "definedTrophies": groups.get("definedTrophies"),
        "hasTrophyGroups": groups.get("hasTrophyGroups"),
        "npServiceName": service_name,
        "includeUserData": TROPHY_INCLUDE_USER_DATA,
        "userTrophiesError": user_data_error if (TROPHY_INCLUDE_USER_DATA and not user_data) else None,
        "includeGameHelp": TROPHY_INCLUDE_GAME_HELP,
        "saveDuplicateLocales": TROPHY_SAVE_DUPLICATE_LOCALES,
        "requestedLanguages": [{"folder": f, "acceptLanguage": h, "label": l} for f, h, l in languages],
        "successfulLocaleCount": len(successful),
        "uniqueLocalizedContentCount": len(unique_signatures),
        "localeAliases": {l["folder"]: l["sameContentAs"] for l in successful if l.get("sameContentAs")},
        "locales": locales,
    }

    trophy_save_json_if_changed(trophy_manifest_path(npcid), manifest)
    trophy_append_valid_log(npcid, title, platform)

    async with counter_lock:
        checked_counter[0] += 1
        found_counter[0] += 1
        sys.stdout.write(f"\rChecked IDs: {checked_counter[0]} / {checked_counter[1]} | Found trophies: {found_counter[0]}")
        sys.stdout.flush()

async def scrape_trophies(npsso_token):
    os.makedirs(TROPHY_DIR, exist_ok=True)
    os.makedirs(TROPHY_META_DIR, exist_ok=True)

    async with aiohttp.ClientSession() as session:
        auth_state = {"npsso": npsso_token, "access_token": None, "refresh_token": None, "version": 0}
        auth_lock = asyncio.Lock()
        try:
            code = await trophy_exchange_npsso_for_code(session, npsso_token)
            tokens = await trophy_exchange_code_for_tokens(session, code)
        except Exception as e:
            logging.error(f"PSN authentication failed: {e}")
            print(f"Authentication failed: {e}")
            return
        auth_state["access_token"] = tokens["access_token"]
        auth_state["refresh_token"] = tokens.get("refresh_token")

        languages = TROPHY_LANGUAGES
        total = TROPHY_ID_END - TROPHY_ID_START + 1
        checked_counter = [0, total]
        found_counter = [0]
        counter_lock = asyncio.Lock()
        semaphore = asyncio.Semaphore(TROPHY_CONCURRENCY)

        async def run_one(npcid):
            async with semaphore:
                await trophy_scrape_id(session, auth_state, auth_lock, npcid, languages, counter_lock, checked_counter, found_counter)

        tasks = [run_one(trophy_format_npwr(i)) for i in range(TROPHY_ID_START, TROPHY_ID_END + 1)]
        await asyncio.gather(*tasks)

    sys.stdout.write(f"\rChecked IDs: {checked_counter[0]} / {checked_counter[1]} | Found trophies: {found_counter[0]}")
    print()
    logging.info(f"Saved {found_counter[0]} trophy sets to '{TROPHY_DIR}' (checked {checked_counter[0]} IDs from {trophy_format_npwr(TROPHY_ID_START)} to {trophy_format_npwr(TROPHY_ID_END)})")

def menu():
    print("""
1. All Platforms (TMDB)
2. Only PS3 (TMDB)
3. Only PS4 (TMDB)
4. Only PS1 / PS2 (TMDB)
5. Specific ID (i.e. CUSA12345) (TMDB)
6. Specific Prefix (i.e. CUSA) (TMDB)
7. Download Specific ID images/files
8. Download All icons/images/files for found IDs (Requires pre-scraped files)
9. Only PS3 Updates
10. Only PS4 Updates
11. Only PS Vita Updates
12. Updates for Specific ID (i.e. BLUS30145 / CUSA00001)
13. Updates for Specific Prefix (i.e. BLUS / CUSA)
14. Title Small Storage files
15. Trophies (Requires NPSSO token)
""")
    return input("Choose Option: ").strip()

async def main():
    while True:
        choice = menu()
        dev = get_tmdb_domain() if choice in ("1", "2", "3", "4", "5", "6", "7", "8", "dev", "ps5", "psp", "psp2") else False
        path, ext = get_tmdb_version(choice == "psp2") if choice in ("2", "3", "4", "5", "6", "7", "dev", "ps5", "psp", "psp2") else (None, None)

        if choice == "1":
            await scrape(ps1_ps2_prefixes() + ps3_prefixes(), "tmdb", "xml", dev=dev)
            await scrape(ps4_prefixes(), "tmdb2", "json", dev=dev)
        elif choice == "2":
            await scrape(ps3_prefixes(), path, ext, dev=dev)
        elif choice == "3":
            await scrape(ps4_prefixes(), path, ext, dev=dev)
        elif choice == "4":
            await scrape(ps1_ps2_prefixes(), path, ext, dev=dev)
        elif choice == "ps5":
            await scrape(ps5_prefixes(), path, ext, dev=dev) # nothing, possibly uses some kind of newer api
        elif choice == "psp":
            await scrape(psp_prefixes(), path, ext, dev=dev) # only ULJM05170, ULJM05277, ULJM05353 all empty
        elif choice == "psp2":
            await scrape(psvita_prefixes(), path, ext, dev=dev) # 0 json, only empty PCSF00178.xml came up lol
        elif choice == "5":
            tid = input("Enter Title ID: ").strip().upper()
            if not tid:
                print("Input cannot be empty!")
                continue
            await scrape([tid], path, ext, brute=False, dev=dev)
        elif choice == "6":
            prefix = input("Enter Prefix: ").strip().upper()
            if not prefix:
                print("Input cannot be empty!")
                continue
            await scrape([prefix], path, ext, brute=True, dev=dev)
        elif choice == "7":
            tid = input("Enter Title ID to download images for: ").strip().upper()
            if not tid:
                continue
            async with aiohttp.ClientSession() as session:
                await process_images_for_game(session, tid, ext, dev=dev)
        elif choice == "8":
            await bulk_download_images(dev=dev)
        elif choice == "9":
            await scrape_updates(ps3_prefixes())
        elif choice == "10":
            await scrape_updates(ps4_prefixes())
        elif choice == "11":
            await scrape_updates(psvita_prefixes())
        elif choice == "12":
            tid = input("Enter Title ID: ").strip().upper()
            if not tid:
                print("Input cannot be empty!")
                continue
            await scrape_updates([tid], brute=False)
        elif choice == "13":
            prefix = input("Enter Prefix: ").strip().upper()
            if not prefix:
                print("Input cannot be empty!")
                continue
            await scrape_updates([prefix], brute=True, platform=get_update_backend())
        elif choice == "14":
            await scrape_tss()
        elif choice == "15":
            token = input("Enter your NPSSO token (From https://ca.account.sony.com/api/v1/ssocookie): ").strip()
            if not token:
                print("Input cannot be empty!")
                continue
            await scrape_trophies(token)
        elif choice == "dev":
            await scrape(dev_prefixes(), path, ext, dev=dev)
            for update_backend in ("PS3", "PS4", "PSVita"):
                await scrape_updates(dev_prefixes(), platform=update_backend)
        else:
            print("Invalid Option")
            continue

        again = input("\nDo you want to do something else? (y/n): ").strip().lower()
        if again not in ("y", "yes"):
            print("Exiting program...")
            break

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.warning("[INTERRUPTED] Stopped by user (Ctrl+C)")

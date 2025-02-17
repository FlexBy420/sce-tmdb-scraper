import aiohttp
import asyncio
import hashlib
import hmac
import logging
import os
from itertools import product

os.makedirs("log", exist_ok=True)
os.makedirs("xml", exist_ok=True)
os.makedirs("json", exist_ok=True)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log_file_path = os.path.join("log", "log.txt")
file_handler = logging.FileHandler(log_file_path)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(file_handler)

FOUND_FILE = os.path.join("log", "found_links.txt")

DOMAIN = "http://tmdb.np.dl.playstation.net/"
SECRET_KEY = bytes.fromhex(
    "F5DE66D2680E255B2DF79E74F890EBF349262F618BCAE2A9ACCDEE5156CE8DF2CDF2D48C71173CDC2594465B87405D197CF1AED3B7E9671EEB56CA6753C2E6B0"
)
MAX_CONCURRENT_REQUESTS = 2000

# Generate HMAC hash
def generate_hash(title_id):
    return hmac.new(SECRET_KEY, f"{title_id.upper()}_00".encode(), hashlib.sha1).hexdigest().upper()

# Fetch and download TMDB data
async def fetch_tmdb(session, semaphore, title_id, path, extension):
    async with semaphore:
        url = f"{DOMAIN}{path}/{title_id}_00_{generate_hash(title_id)}/{title_id}_00.{extension}"
        logging.info(f"Checking URL: {url}")
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    file_path = f"{extension}/{title_id}.{extension}"
                    with open(file_path, "wb") as file:
                        file.write(await response.read())
                    logging.info(f"Downloaded {title_id} to {file_path}") # Some XML and JSON files are just empty
                    with open(FOUND_FILE, "a") as log:
                        log.write(f"{title_id}: {url}\n")
        except Exception as e:
            logging.error(f"Error for {title_id}: {e}")

# Scrape PSX, PS2, PS3, and PS4 IDs
async def scrape_all_ids():
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    ps3_digital = [f"NP{region}{rtype}" for region, rtype in product("EHJKU", "ABCDEFGHIJKLMNOPQRSTUVWXYZ")] # A in region never been used it seems
    ps3_physical = [f"B{rights}{region}{rtype}" for rights, region, rtype in product("CL", "AEJKU", "BCDMSX") if not ((rtype in ["M", "B"]) and region != "J")] # C, H in region never been used it seems
    ps3_mrtc = [f"MRTC"]
    psx_ps2_physical = [f"S{rights}{region}{rtype}" for rights, region, rtype in product("CL", "ACEKPUZ", "ADJMNS")] # Other ones than these appear not be used? e.g. PAPX
    ps4_prefixes = [f"CUSA"]
    #ps5_prefixes = [f"PPSA"]

    async with aiohttp.ClientSession() as session:
        for prefixes, path, ext in [
            (psx_ps2_physical + ps3_physical + ps3_mrtc + ps3_digital, "tmdb", "xml"), # PSP and VITA may use this one too?
            (ps4_prefixes, "tmdb2", "json")
            #(ps5_prefixes, "tmdb3", "json") # Seems to be a thing, needs API key
        ]:
            for prefix in prefixes:
                logging.info(f"Scraping {path.upper()} for prefix: {prefix}")
                tasks = [fetch_tmdb(session, semaphore, f"{prefix}{i:05}", path, ext) for i in range(100000)]
                await asyncio.gather(*tasks)

async def main():
    logging.info("Starting scrape for all IDs...")
    await scrape_all_ids()
    logging.info("Scraping completed.")

if __name__ == "__main__":
    asyncio.run(main())
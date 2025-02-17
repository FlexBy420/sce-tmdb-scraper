import aiohttp
import asyncio
import hashlib
import hmac

DOMAIN = "http://tmdb.np.dl.playstation.net/"
PATH = "tmdb"
SECRET_KEY = bytes.fromhex(
    "F5DE66D2680E255B2DF79E74F890EBF349262F618BCAE2A9ACCDEE5156CE8DF2CDF2D48C71173CDC2594465B87405D197CF1AED3B7E9671EEB56CA6753C2E6B0"
)
LOG_FILE = "found_ids.txt"
MAX_CONCURRENT_REQUESTS = 10  # Adjust this value based on the rate limit

# Define valid prefixes
class MediaRules:
    @staticmethod
    def is_valid_digital_ps3(prefix):
        if len(prefix) != 4:
            return False
        network_env = prefix[0:2]  # ('NP')
        region = prefix[2]  # 3rd character (e.g., 'A', 'E', 'H', etc.)
        r_type = prefix[3]  # 4th character (e.g., 'A', 'B', 'C', etc.)

        valid_network_env = network_env == "NP"
        valid_regions = ["A", "E", "H", "J", "K", "U", "I", "X"]
        valid_r_types = [
            "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O", "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z"
        ]

        return valid_network_env and region in valid_regions and r_type in valid_r_types

    @staticmethod
    def is_valid_physical_ps3(prefix):
        if len(prefix) != 4:
            return False
        media = prefix[0]  # ('B')
        rights = prefix[1]  # 2nd character (e.g., 'C', 'L')
        region = prefix[2]  # 3rd character (e.g., 'A', 'C', 'E', etc.)
        r_type = prefix[3]  # 4th character (e.g., 'M', 'S')

        valid_media = media == "B"
        valid_rights = rights in ["C", "L"]
        valid_regions = ["A", "C", "E", "H", "J", "K", "P", "U"]
        valid_r_types = ["M", "S"]

        # 'M' is only valid with region 'J'
        if r_type == "M" and region != "J":
            return False

        return valid_media and valid_rights and region in valid_regions and r_type in valid_r_types

    @staticmethod
    def is_valid_physical_psx_ps2(prefix):
        if len(prefix) != 4:
            return False
        media = prefix[0]  # ('S')
        rights = prefix[1]  # 2nd character (e.g., 'C', 'L')
        region = prefix[2]  # 3rd character (e.g., 'A', 'C', 'E', etc.)
        r_type = prefix[3]  # 4th character (e.g., 'A', 'D')

        valid_media = media == "S"
        valid_rights = rights in ["C", "L"]
        valid_regions = ["A", "C", "E", "K", "P", "U", "Z"]
        valid_r_types = ["A", "D", "J", "M", "N", "S"]

        return valid_media and valid_rights and region in valid_regions and r_type in valid_r_types

    @staticmethod
    def generate_all_valid_prefixes():
        valid_prefixes = []
        # PS3 digital
        network_env = "NP"
        valid_regions = ["A", "E", "H", "J", "K", "U", "I", "X"]
        valid_r_types = [
            "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O", "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z"
        ]
        for region in valid_regions:
            for r_type in valid_r_types:
                valid_prefixes.append(f"{network_env}{region}{r_type}")
        # PS3 disc
        media = "B"
        valid_rights = ["C", "L"]
        valid_regions = ["A", "C", "E", "H", "J", "K", "P", "U"]
        valid_r_types = ["M", "S"]
        for rights in valid_rights:
            for region in valid_regions:
                for r_type in valid_r_types:
                    if r_type == "M" and region != "J":
                        continue
                    valid_prefixes.append(f"{media}{rights}{region}{r_type}")
        # PS1 and PS2
        media = "S"
        valid_rights = ["C", "L"]
        valid_regions = ["A", "C", "E", "K", "P", "U", "Z"]
        valid_r_types = ["A", "D", "J", "M", "N", "S"]
        for rights in valid_rights:
            for region in valid_regions:
                for r_type in valid_r_types:
                    valid_prefixes.append(f"{media}{rights}{region}{r_type}")

        return valid_prefixes

# Generate HMAC hash for the title ID
def generate_hash(title_id):
    title_id_upper = title_id.upper() + "_00"
    hmac_obj = hmac.new(SECRET_KEY, title_id_upper.encode("utf-8"), hashlib.sha1)
    return hmac_obj.hexdigest().upper()

# Fetch TMDb XML
async def fetch_tmdb_xml(session, semaphore, title_id):
    async with semaphore:
        title_id_with_suffix = title_id + "_00"
        hash_value = generate_hash(title_id)
        url = f"{DOMAIN}{PATH}/{title_id_with_suffix}_{hash_value}/{title_id_with_suffix}.xml"
        print(f"Trying: {url}")
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    print(f"Success: Found XML for {title_id}")
                    xml_data = await response.text()
                    with open(LOG_FILE, "a") as log:
                        log.write(f"{title_id}: {url}\n")
                    return xml_data
                else:
                    print(f"Failed: {title_id} returned status {response.status}")
        except Exception as e:
            print(f"Error fetching {title_id}: {e}")
        return None

# Scrape IDs for a given prefix
async def scrape_ids(prefix):
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    async with aiohttp.ClientSession() as session:
        tasks = []
        for num in range(0, 100000):
            title_id = f"{prefix}{num:05}"
            tasks.append(fetch_tmdb_xml(session, semaphore, title_id))

        results = await asyncio.gather(*tasks)
        for result in results:
            if result:
                print(f"Found XML data: {result[:500]}...\n")

# Scrape all valid prefixes
async def scrape_all_prefixes():
    valid_prefixes = MediaRules.generate_all_valid_prefixes()
    for prefix in valid_prefixes:
        print(f"Scraping prefix: {prefix}")
        await scrape_ids(prefix)

async def main():
    while True:
        choice = input("Do you want to scrape all valid IDs? (y/n): ").strip().lower()
        if choice == 'y':
            await scrape_all_prefixes()
        else:
            start_id = input("Enter starting ID (e.g. BCUS12345): ").strip().upper()
            if len(start_id) != 9 or not start_id[4:9].isdigit():
                print("Invalid ID format. Please use valid PS3 format.")
            else:
                await scrape_ids(start_id[:4])

        print("Scraping completed!")
        another = input("Do you want to perform another scraping session? (y/n): ").strip().lower()
        if another != 'y':
            print("Exiting the script. Goodbye!")
            break

if __name__ == "__main__":
    asyncio.run(main())
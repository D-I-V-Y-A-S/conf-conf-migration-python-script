import requests
import re
from requests.auth import HTTPBasicAuth

# --- CONFIGURATION ---
# --- SOURCE CONFLUENCE CONFIG ---
dest_base_url = 
dest_email = 
dest_api_token = 

# --- DESTINATION CONFLUENCE CONFIG ---
source_base_url = 
source_email = 
source_api_token =

# Headers
space_key = "MNO"
headers = {"Content-Type": "application/json"}

# --- CLEAN SPACE KEY ---
def clean_space_key(key):
    key = re.sub(r'[^a-zA-Z0-9]', '_', key)
    return key[:255]

# --- FETCH SPACE DETAILS ---
def get_space_details(key):
    url = f"{source_base_url}/rest/api/space/{key}?expand=description.plain"
    response = requests.get(url, auth=HTTPBasicAuth(source_email, source_api_token))
    if response.status_code == 200:
        return response.json()
    else:
        print(f"❌ Could not fetch space {key}: {response.status_code} - {response.text}")
        return None

# --- CREATE SPACE IN DESTINATION ---
def create_space(key, name, description):
    payload = {
        "key": key,
        "name": name,
        "description": {
            "plain": {
                "value": description,
                "representation": "plain"
            }
        }
    }
    url = f"{dest_base_url}/rest/api/space"
    response = requests.post(url, auth=HTTPBasicAuth(dest_email, dest_api_token), headers=headers, json=payload)
    if response.status_code in [200, 201]:
        print(f"✅ Created space: {key}")
        return True
    else:
        print(f"❌ Failed to create space {key}: {response.status_code} - {response.text}")
        return False

# --- FETCH ALL PAGES ---
def get_pages(space_key):
    url = f"{source_base_url}/rest/api/content?spaceKey={space_key}&expand=body.storage,ancestors&limit=50"
    all_pages = []
    while url:
        response = requests.get(url, auth=HTTPBasicAuth(source_email, source_api_token))
        if response.status_code == 200:
            data = response.json()
            all_pages.extend(data.get("results", []))
            next_link = data.get("_links", {}).get("next")
            if next_link:
                url = source_base_url + next_link
            else:
                break
        else:
            print(f"❌ Failed to fetch pages: {response.status_code}")
            break
    return all_pages

# --- CREATE PAGE IN DESTINATION ---
def create_page(space_key, title, body, parent_id=None):
    payload = {
        "type": "page",
        "title": title,
        "space": {"key": space_key},
        "body": {
            "storage": {
                "value": body,
                "representation": "storage"
            }
        }
    }
    if parent_id:
        payload["ancestors"] = [{"id": parent_id}]
    response = requests.post(
        f"{dest_base_url}/rest/api/content",
        auth=HTTPBasicAuth(dest_email, dest_api_token),
        headers=headers,
        json=payload
    )
    if response.status_code in [200, 201]:
        page_id = response.json().get("id")
        print(f"📄 Created page: {title} → ID: {page_id}")
        return page_id
    else:
        print(f"❌ Failed to create page {title}: {response.status_code} - {response.text}")
        return None

# --- ATTACHMENTS ---
def get_attachments(page_id):
    url = f"{source_base_url}/rest/api/content/{page_id}/child/attachment"
    response = requests.get(url, auth=HTTPBasicAuth(source_email, source_api_token))
    return response.json().get("results", []) if response.status_code == 200 else []

def download_attachment(download_url):
    response = requests.get(download_url, auth=HTTPBasicAuth(source_email, source_api_token))
    return response.content if response.status_code == 200 else None

def upload_attachment(dest_page_id, filename, file_bytes, mime_type="application/octet-stream"):
    files = {'file': (filename, file_bytes, mime_type)}
    headers = {"X-Atlassian-Token": "no-check"}
    url = f"{dest_base_url}/rest/api/content/{dest_page_id}/child/attachment"
    response = requests.post(url, auth=HTTPBasicAuth(dest_email, dest_api_token), files=files, headers=headers)
    if response.status_code in [200, 201]:
        print(f"📎 Uploaded attachment: {filename}")
    else:
        print(f"❌ Failed to upload attachment {filename}: {response.status_code} - {response.text}")

# --- MIGRATE SPACE, PAGES, ATTACHMENTS ---
def migrate_space(space_key):
    space = get_space_details(space_key)
    if not space:
        return
    name = space["name"]
    desc = space.get("description", {}).get("plain", {}).get("value", "Migrated from source Confluence")
    dest_key = clean_space_key(space_key)

    if not create_space(dest_key, name, desc):
        return

    pages = get_pages(space_key)
    id_map = {}

    for page in pages:
        old_id = page["id"]
        title = page["title"]
        body = page["body"]["storage"]["value"]
        parent_id = None
        if page.get("ancestors"):
            parent_old_id = page["ancestors"][-1]["id"]
            parent_id = id_map.get(parent_old_id)

        new_id = create_page(dest_key, title, body, parent_id)
        if new_id:
            id_map[old_id] = new_id

            # Attachments
            attachments = get_attachments(old_id)
            for att in attachments:
                file_url = source_base_url + att["_links"]["download"]
                file_name = att["title"]
                content = download_attachment(file_url)
                if content:
                    upload_attachment(new_id, file_name, content)

# --- MAIN EXECUTION ---
migrate_space(space_key)

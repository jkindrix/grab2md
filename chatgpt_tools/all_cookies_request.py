#!/usr/bin/env python3
import json
import requests
from urllib.parse import urlparse

# Load all cookies from the JSON file
with open('cookies.json', 'r') as f:
    cookies_data = json.load(f)

# Create a session
s = requests.Session()

# Add all cookies from the file
for cookie in cookies_data:
    if isinstance(cookie, dict) and 'name' in cookie and 'value' in cookie:
        domain = cookie.get('domain', '')
        # Remove leading dot from domain if present
        if domain.startswith('.'):
            domain = domain[1:]
        path = cookie.get('path', '/')
        
        # Set cookie in the session
        s.cookies.set(
            cookie['name'],
            cookie['value'],
            domain=domain,
            path=path
        )
        print(f"Added cookie: {cookie['name']} for domain {domain}")

# Set realistic browser headers
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://chatgpt.com/',
    'Cache-Control': 'max-age=0',
    'Sec-CH-UA': '"Google Chrome";v="123", "Not:A-Brand";v="8", "Chromium";v="123"',
    'Sec-CH-UA-Mobile': '?0',
    'Sec-CH-UA-Platform': '"Windows"',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'same-origin',
    'Sec-Fetch-User': '?1',
    'Upgrade-Insecure-Requests': '1',
    'Connection': 'keep-alive'
}

# Make the request
conversation_id = '6812d27d-6498-8006-9c6e-e6b6a4d6c0eb'
url = f'https://chatgpt.com/c/{conversation_id}'

print(f"Requesting: {url}")
print(f"Using {len(s.cookies)} cookies")

r = s.get(url, headers=headers)

# Print status and response info
print(f'Status: {r.status_code}')
print(f'Content-Type: {r.headers.get("content-type", "unknown")}')
print(f'Response length: {len(r.text)} bytes')

# Save the response to a file
with open('all_cookies_response.html', 'w') as f:
    f.write(r.text)

# Save response info to a separate file
with open('all_cookies_info.txt', 'w') as f:
    f.write(f'Status: {r.status_code}\n')
    f.write(f'Content-Type: {r.headers.get("content-type", "unknown")}\n')
    f.write(f'Response length: {len(r.text)} bytes\n')
    f.write('\nResponse Headers:\n')
    for header, value in r.headers.items():
        f.write(f'{header}: {value}\n')
    f.write('\nCookies Used:\n')
    for cookie in s.cookies:
        f.write(f'{cookie.name}: {cookie.value} (domain: {cookie.domain})\n')

print(f'Response saved to all_cookies_response.html')
print(f'Response info saved to all_cookies_info.txt')

# Try the API endpoint directly if the main page fails
if r.status_code != 200 or len(r.text) < 1000:
    print("\nAttempting API endpoint approach...")
    
    api_url = f"https://chatgpt.com/backend-api/conversation/{conversation_id}"
    api_headers = headers.copy()
    api_headers.update({
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Requested-With": "XMLHttpRequest"
    })
    
    print(f"Requesting API: {api_url}")
    api_response = s.get(api_url, headers=api_headers)
    
    print(f'API Status: {api_response.status_code}')
    print(f'API Content-Type: {api_response.headers.get("content-type", "unknown")}')
    print(f'API Response length: {len(api_response.text)} bytes')
    
    # Save the API response to a file
    with open('all_cookies_api_response.json', 'w') as f:
        f.write(api_response.text)
    
    # Save API response info to a separate file
    with open('all_cookies_api_info.txt', 'w') as f:
        f.write(f'Status: {api_response.status_code}\n')
        f.write(f'Content-Type: {api_response.headers.get("content-type", "unknown")}\n')
        f.write(f'Response length: {len(api_response.text)} bytes\n')
        f.write('\nResponse Headers:\n')
        for header, value in api_response.headers.items():
            f.write(f'{header}: {value}\n')
    
    print(f'API response saved to all_cookies_api_response.json')
    print(f'API info saved to all_cookies_api_info.txt')

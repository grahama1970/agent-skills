import requests
def fetch_url(url: str):
    return requests.get(url, timeout=5)

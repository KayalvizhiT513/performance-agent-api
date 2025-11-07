import requests

def read_web_page(url: str) -> str:
    """
    Fetch the content of a web page.
    """
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        raise RuntimeError(f"Failed to fetch web page: {e}")

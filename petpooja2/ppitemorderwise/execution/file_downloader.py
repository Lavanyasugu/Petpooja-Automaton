import requests
import os
import json

def download_file(url, target_path):
    """
    Downloads a file from a URL to a target path.
    """
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        
        with open(target_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"Download failed: {str(e)}")
        return False

if __name__ == "__main__":
    # Test download
    # download_file("https://example.com/file.csv", "test.csv")
    pass

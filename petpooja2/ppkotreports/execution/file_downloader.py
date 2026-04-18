import requests
import os
import json

def download_file(url: str, target_path: str) -> bool:
    """
    Downloads a file from a URL or copies it if it's already a local path.
    """
    try:
        if os.path.exists(url) and os.path.isfile(url):
            # If it's already local, just copy it to target
            if os.path.abspath(url) == os.path.abspath(target_path):
                return True
            import shutil
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            shutil.copy(url, target_path)
            return True
            
        # Actual HTTP request
        response = requests.get(url, stream=True, timeout=60)
        response.raise_for_status()
        
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        
        with open(target_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk: # filter out keep-alive new chunks
                    f.write(chunk)
        return True
    except Exception as e:
        print(f"Download failed: {str(e)}")
        return False

if __name__ == "__main__":
    # Test download
    # download_file("https://example.com/file.csv", "test.csv")
    pass

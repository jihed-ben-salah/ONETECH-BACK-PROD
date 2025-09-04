import requests
with open(r"C:\Users\jihed\OneDrive\Bureau\Extraction\images\NPT\samples-1-14_page-0001.jpg","rb") as f:
    r = requests.post(
        "https://onetech-back-prod.onrender.com/extract/",
        files={"file": f},
        data={"document_type":"NPT"},
        timeout=180
    )
print(r.status_code, r.json())
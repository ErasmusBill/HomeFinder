import urllib.request

try:
    response = urllib.request.urlopen('http://localhost:8000/pricing/')
    print("Pricing page status code:", response.getcode())
except Exception as e:
    print("Error:", e)

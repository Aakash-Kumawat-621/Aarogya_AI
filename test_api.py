import requests
payload = {
    'symptoms_text': 'chest pain',
    'patient': '{"name":"Test","age":45,"gender":"male","smoking":"never","conditions":[]}'
}
# Need multipart/form-data because FastAPI expects Form(...)
res = requests.post(
    'http://localhost:8000/api/v1/analyze',
    data=payload,
    files={'dummy': ('', '')} # force multipart
)
print(res.text)

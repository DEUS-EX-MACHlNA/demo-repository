# vLLM Colab serving code

## 1. 라이브러리 재구성

```
pip -q uninstall -y tensorflow google-ai-generativelanguage grpcio-status
pip -q install -U "protobuf==6.33.5" vllm ngrok

```

## 2. 라이브러리 확인

```
python -c "import google.protobuf; print(google.protobuf.__version__)"
python -c "import vllm; print(vllm.__version__)"

```

## 3. 요구 라이브러리 설치

```
pip -q install -U vllm pyngrok

```

## 4. 환경변수 설정

### 1) 코랩 환경변수로 설정

NGROK_AUTHTOKEN

VLLM_BASE_URL = "https://nontheatrical-judiciarily-susanne.ngrok-free.dev/v1"

VLLM_MODEL = "Qwen/Qwen2.5-7B-Instruct"

VLLM_API_KEY = "EMPTY"

### 2) 터미널에서 설정

```
export NGROK_AUTHTOKEN=""
echo $NGROK_AUTHTOKEN
나머지 동일
```

## 5. NGROK 연결

노트북 셀에서 아래 코드 실행.

```
from pyngrok import ngrok
from google.colab import userdata

ngrok.set_auth_token(userdata.get("NGROK_AUTHTOKEN"))
public_url = ngrok.connect(8000, "http")
print(public_url)
```

## 6. VLLM 실행

터미널에서 아래 코드 실행.

```
python -m vllm.entrypoints.openai.api_server \
  --host 0.0.0.0 --port 8000 \
  --model "$MODEL" \
  --served-model-name "$MODEL" \
  --dtype auto \
  --max-model-len 8192 \
  > vllm.log 2>&1 &
```

## 7. 확인

```
lsof -i :8000
kill <PID>
```

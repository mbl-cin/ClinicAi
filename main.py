# main.py - VERSÃO PARA META (WHATSAPP CLOUD API)

import os
import requests
import pymongo
from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, AIMessage
from agent import TriageAgent

load_dotenv()

# --- Configurações ---
APP_SECRET = os.getenv("WHATSAPP_VERIFY_TOKEN")
PAGE_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")

# --- Conexão com o Banco de Dados ---
try:
    client = pymongo.MongoClient(MONGO_URI)
    db = client.clinicai
    conversations_collection = db.conversations
    print("Conexão com o MongoDB estabelecida com sucesso.")
except Exception as e:
    print(f"Erro ao conectar ao MongoDB: {e}")

# --- Inicialização ---
app = FastAPI()
triage_agent = TriageAgent()

# --- Funções Auxiliares ---
def get_conversation_history(phone_number: str) -> list:
    conversation = conversations_collection.find_one({"phone_number": phone_number})
    if not conversation: return []
    history = []
    for msg in conversation.get("messages", []):
        if msg["role"] == "user": history.append(HumanMessage(content=msg["content"]))
        else: history.append(AIMessage(content=msg["content"]))
    return history

def save_message_to_history(phone_number: str, user_message: str, ai_message: str):
    conversations_collection.update_one(
        {"phone_number": phone_number},
        {"$push": {"messages": {"$each": [{"role": "user", "content": user_message}, {"role": "ai", "content": ai_message}]}}},
        upsert=True
    )

def send_whatsapp_message(to: str, message: str):
    url = f"https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {PAGE_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    data = {
        "messaging_product": "whatsapp",
        "to": to,
        "text": {"body": message},
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code != 200:
        print(f"Erro ao enviar mensagem: {response.status_code} {response.text}")
    else:
        print(f"Mensagem enviada com sucesso para {to}")

# --- Endpoints da API ---
@app.get("/")
def read_root():
    return {"message": "ClinicAI Triage Agent is running."}

@app.get("/webhook")
def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    if mode == "subscribe" and token == APP_SECRET:
        print("WEBHOOK VERIFICADO COM SUCESSO!")
        return int(challenge)
    print("ERRO DE VERIFICAÇÃO DO WEBHOOK.")
    raise HTTPException(status_code=403, detail="Verification token mismatch")

@app.post("/webhook")
async def handle_webhook(request: Request):
    data = await request.json()
    print("Dados recebidos do webhook:", data)
    try:
        if data.get("object") == "whatsapp_business_account":
            for entry in data.get("entry", []):
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    if value.get("messages"):
                        message_data = value["messages"][0]
                        if message_data.get("type") == "text":
                            from_number = message_data["from"]
                            user_msg_text = message_data["text"]["body"]
                            print(f"Mensagem recebida de {from_number}: {user_msg_text}")
                            history = get_conversation_history(from_number)
                            history.append(HumanMessage(content=user_msg_text))
                            ai_response = triage_agent.run(history)
                            ai_response_text = ai_response.content
                            send_whatsapp_message(from_number, ai_response_text)
                            save_message_to_history(from_number, user_msg_text, ai_response_text)
    except Exception as e:
        print(f"Erro ao processar a mensagem: {e}")
    return {"status": "ok"}
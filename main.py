import os
import asyncio
import functions_framework
from flask import jsonify
import uuid
import logging

logging.basicConfig(level=logging.INFO)

# --- CONFIGURAÇÃO 2026 ---
PROJECT_ID = "atalaya-elias-v2"
LOCATION = "us-central1"

os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true"
os.environ["GOOGLE_CLOUD_PROJECT"] = PROJECT_ID
os.environ["GOOGLE_CLOUD_LOCATION"] = LOCATION

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import VertexAiSearchTool

class EstiloMensagem:
    def __init__(self, role, text):
        self.role = role
        self.parts = [type('Part', (), {'text': text})()]

# Ferramenta de busca
search_tool = VertexAiSearchTool(
    data_store_id='projects/582836671682/locations/global/collections/default_collection/dataStores/ds-atalaya24-clientes-v2_1772385126826'
)

elias_agent = LlmAgent(
    name='ASISTENTE_Atalaya24',
    model='gemini-2.5-flash', 
    instruction="""Você é o Elias, assistente da Atalaya 24.
    Sua missão é ajudar os clientes com base nos manuais.
    REGRAS CRÍTICAS:
    1. Responda SEMPRE no mesmo idioma da pergunta do usuário.
    2. Se não encontrar a informação exata, diga que está consultando os especialistas.
    3. Seja direto e profissional.""",
    tools=[search_tool]
)

session_service = InMemorySessionService()
runner = Runner(agent=elias_agent, app_name="AtalayaChat", session_service=session_service)

@functions_framework.http
def atalaya_webhook(request):
    return asyncio.run(atalaya_handler(request))

async def atalaya_handler(request):
    if request.method == 'OPTIONS':
        return ('', 204, {'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Methods': 'POST', 'Access-Control-Allow-Headers': 'Content-Type'})
    
    headers = {'Access-Control-Allow-Origin': '*'}
    try:
        request_json = request.get_json(silent=True)
        msg_text = request_json.get('mensagem', 'Olá')

        u_id = "user_web"
        s_id = str(uuid.uuid4())
        await session_service.create_session(app_name="AtalayaChat", user_id=u_id, session_id=s_id)
        
        structured_message = EstiloMensagem(role="user", text=msg_text)
        
        # --- COLETA ROBUSTA DE RESPOSTA ---
        texto_acumulado = []
        
        # O runner.run pode gerar vários eventos até chegar na resposta final
        events = runner.run(user_id=u_id, session_id=s_id, new_message=structured_message)
        
        for event in events:
            # 1. Tenta pegar texto direto do evento
            if hasattr(event, 'text') and event.text:
                texto_acumulado.append(str(event.text))
            
            # 2. Tenta pegar texto dentro do conteúdo (parts)
            content = getattr(event, 'content', None)
            if content and hasattr(content, 'parts'):
                for part in content.parts:
                    if hasattr(part, 'text') and part.text:
                        texto_acumulado.append(str(part.text))

        resposta_final = "".join(texto_acumulado).strip()

        if not resposta_final:
            # Se ainda estiver vazio, é porque o modelo só chamou a ferramenta mas não respondeu.
            # Vamos dar um "empurrão" final.
            return (jsonify({"resposta": "Elias está processando os manuais para você. Por favor, pergunte novamente em instantes."}), 200, headers)

        return (jsonify({"resposta": resposta_final}), 200, headers)

    except Exception as e:
        logging.error(f"ERRO NO SISTEMA: {str(e)}")
        return (jsonify({"resposta": f"Desculpe, o Elias teve um problema técnico: {str(e)[:50]}"}), 200, headers)
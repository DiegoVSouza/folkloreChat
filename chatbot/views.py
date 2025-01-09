from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from langchain_huggingface import HuggingFaceEndpoint
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain.schema import SystemMessage, HumanMessage, AIMessage
from dotenv import load_dotenv
import uuid
import re
from chatbot.chat_memory import ChatMemory
from chatbot.prompt_data import get_system_prompt
from langchain_core.output_parsers import StrOutputParser
from langchain_community.vectorstores import Chroma
from langchain_community.document_loaders import WebBaseLoader
import os

load_dotenv()
chat_memory = ChatMemory()
os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"

hf_embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

web_paths = [
    "https://brasilescola.uol.com.br/historiab/folclore-brasileiro.htm#:~:text=O%20folclore%20brasileiro%20%C3%A9%20o%20conjunto%20de%20realiza%C3%A7%C3%B5es%20que%20fazem,populares%2C%20jarg%C3%B5es%2C%20literatura%20etc.",
    "https://pt.wikipedia.org/wiki/Folclore_brasileiro",
    "https://www.todamateria.com.br/folclore-brasileiro/",
    "https://www.gov.br/turismo/pt-br/assuntos/noticias/dia-do-saci-descubra-os-encantos-do-folclore-brasileiro",
    "https://mundoeducacao.uol.com.br/cultura-brasileira/folclore.htm",
    "https://pt.wikipedia.org/wiki/Saci",
    "https://pt.wikipedia.org/wiki/Cuca"
]

loader = WebBaseLoader(web_paths=web_paths)
docs = loader.load()

text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200, add_start_index=True)
splits = text_splitter.split_documents(docs)

vectorstore = Chroma.from_documents(documents=splits, embedding=hf_embeddings)

retriever = vectorstore.as_retriever(search_type="similarity", search_kwargs={"k": 6})

def truncate_chat_history(chat_history, max_tokens=4000, buffer_tokens=512):

    max_history_tokens = max_tokens - buffer_tokens
    truncated_history = []
    current_tokens = 0

    for message in reversed(chat_history):
        message_text = f"{message['role'].capitalize()}: {message['content']}"
        message_tokens = len(message_text.split())  
        if current_tokens + message_tokens > max_history_tokens:
            break
        truncated_history.insert(0, message)
        current_tokens += message_tokens

    return truncated_history

def clean_model_output(output):
    cleaned_output = re.sub(r"<\|.*?\|>", "", output)

    final_answer_match = re.search(
        r"(Final Answer|Answer|Resposta Final|Resposta:|Resposta)\s*:\s*(.+)",
        output,
        re.IGNORECASE | re.DOTALL,
    )
    if final_answer_match:
        return final_answer_match.group(2).strip()

    unique_lines = set(cleaned_output.splitlines())
    if len(unique_lines) < len(cleaned_output.splitlines()) * 0.5:  
        return "Erro: a resposta contém padrões repetitivos e não é válida."

    if len(cleaned_output.split()) > 500: 
        return "Erro: a resposta é muito longa e não parece válida."

    return cleaned_output.strip()


def generate_prompt(chat_history, character, user_id, user_query, retriever):
    system_prompt = get_system_prompt(character)

    relevant_contexts = retriever.get_relevant_documents(user_query)
    context_text = "\n".join([doc.page_content for doc in relevant_contexts])

    truncated_history = truncate_chat_history(chat_history)

    messages = [SystemMessage(content=system_prompt)]

    if context_text:
        messages.append(SystemMessage(content=f"Context for reference:\n{context_text}"))

    for message in truncated_history:
        if message["role"] == "human":
            messages.append(HumanMessage(content=message["content"]))
        elif message["role"] == "ai":
            messages.append(AIMessage(content=message["content"]))

    messages.append(HumanMessage(content=user_query))

    return messages



def model_hf_hub(model="meta-llama/Meta-Llama-3-8B-Instruct", temperature=0.1, max_length=512, top_p=0.9):
    llm = HuggingFaceEndpoint(
        repo_id=model,
        temperature=temperature,
        max_length=max_length,
        top_p=top_p,
        stop=["stop_condition"]
    )
    return llm

def model_response(user_query, character, user_id, chat_history):
    try:
        llm = model_hf_hub()

        prompt = generate_prompt(chat_history, character, user_id, user_query, retriever)
        chain = llm | StrOutputParser()
        raw_output = chain.invoke(prompt)
        # response = clean_model_output(raw_output)
        response = raw_output

        if not response or "Erro" in response:
            return "Desculpe, não consegui processar uma resposta válida. Tente reformular sua pergunta."

        return response
    except Exception as e:
        return f"Erro no modelo: {str(e)}"

class ChatAPIView(APIView):
    def post(self, request):
        user_id = request.session.get("user_id")
        if not user_id:
            user_id = str(uuid.uuid4())
            request.session["user_id"] = user_id

        user_query = request.data.get("query")
        character = request.data.get("character")

        if not user_query:
            return Response({"error": "A consulta do usuário é obrigatória."}, status=status.HTTP_400_BAD_REQUEST)
        if not character:
            return Response({"error": "É obrigatório selecionar um personagem."}, status=status.HTTP_400_BAD_REQUEST)

        chat_history = chat_memory.get_chat_history(user_id,character)
        print(chat_history)
        try:
            response = model_response(user_query, character, user_id, chat_history)

            if "Erro" in response:
                return Response({"error": response}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            chat_memory.save_message(user_id, character, "human", user_query)
            chat_memory.save_message(user_id, character, "ai", response)

            return Response({
                "response": response,
                "user_id": user_id
            })
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
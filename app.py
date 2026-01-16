# app.py
import streamlit as st
import requests
import fitz
import io
import urllib3
import anthropic

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# CONFIG

API_URL = "https://consultasentenciascj.poderjudicial.gob.do/Home/GetExpedientes"
FIRST_CHAMBER_ID = 1
PAGE_SIZE = 10
ANTHROPIC_API_KEY = st.secrets.get("ANTHROPIC_API_KEY")


def search_cases(query):
    all_records = []
    start = 0
    total_records = None
    draw = 1
    
    while True:
        payload = {
            "draw": draw,
            "start": start,
            "length": PAGE_SIZE,
            "search[value]": query,
            "search[regex]": "false",
            "IdTribunal": FIRST_CHAMBER_ID,
            "Materia": "",
            "Ano": "",
            "Mes": "",
            "IdTipoDocumento": "",
            "Contenido": query,
        }
        
        for i in range(4):
            payload[f"columns[{i}][data]"] = ""
            payload[f"columns[{i}][name]"] = ""
            payload[f"columns[{i}][searchable]"] = "true"
            payload[f"columns[{i}][orderable]"] = "false"
            payload[f"columns[{i}][search][value]"] = ""
            payload[f"columns[{i}][search][regex]"] = "false"
        
        headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Accept": "application/json",
            "Origin": "https://consultasentenciascj.poderjudicial.gob.do",
            "Referer": "https://consultasentenciascj.poderjudicial.gob.do/",
            "User-Agent": "Mozilla/5.0",
        }
        
        response = requests.post(API_URL, data=payload, headers=headers, timeout=20)
        response.raise_for_status()
        data = response.json()
        
        if total_records is None:
            total_records = data.get("recordsFiltered", 0)
            if total_records == 0:
                return []
        
        current_page = data.get("data", [])
        all_records.extend(current_page)
        
        if start + PAGE_SIZE >= total_records:
            break
        
        start += PAGE_SIZE
        draw += 1
    
    return all_records


def download_and_extract_pdf(url, timeout=30):
    try:
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        
        resp = session.get(url, timeout=timeout, verify=False, allow_redirects=True)
        resp.raise_for_status()
        
        if not resp.content[:5].startswith(b'%PDF'):
            return "[ERROR: El contenido no es un PDF válido]"
        
        pdf_stream = io.BytesIO(resp.content)
        document = fitz.open(stream=pdf_stream, filetype="pdf")
        
        text_content = ""
        for page in document:
            text_content += page.get_text()
        document.close()
        
        return text_content.strip()
    
    except Exception as e:
        return f"[ERROR: {str(e)}]"



# INTERFACE

st.set_page_config(page_title="Asistente Sentencias Primera Sala", layout="wide")

try:
    st.markdown(
        """
        <style>
            [data-testid="stSidebarNav"] {
                background-image: url('https://poderjudicial.gob.do/wp-content/uploads/2022/09/Logo-Poder-Judicial@3x.png');
                background-repeat: no-repeat;
                padding-top: 60px;
                background-position: center 10px;
                background-size: 140px;
            }
            [data-testid="stSidebarNav"]::before {
                content: "";
            }
        </style>
        """,
        unsafe_allow_html=True
    )
except:
    pass

col_logo, _ = st.columns([1, 5])
with col_logo:
    st.image(
        "https://poderjudicial.gob.do/wp-content/uploads/2022/09/Logo-Poder-Judicial@3x.png",
        width=140,
        caption="Poder Judicial"
    )

st.title("Asistente de Sentencias - Primera Sala de la SCJ")
st.markdown("Busca expedientes por palabra clave y luego consulta sobre los documentos encontrados.")

col_search, col_limit = st.columns([3, 1])
with col_search:
    search_term = st.text_input("- - Término de búsqueda:", placeholder="Ej: divorcio, herencia, pensión alimenticia, etc.")
with col_limit:
    max_documents = st.slider("Máx. documentos a procesar", 1, 20, 5)

if st.button("Buscar y procesar documentos", type="primary", use_container_width=True) or 'results' in st.session_state:
    if not search_term:
        st.warning("Por favor ingresa un término de búsqueda.")
    else:
        with st.spinner("Buscando y descargando expedientes..."):
            if 'last_search' not in st.session_state or st.session_state.last_search != search_term:
                st.session_state.results = search_cases(search_term)
                st.session_state.last_search = search_term
                st.session_state.parsed_docs = []
                st.session_state.status_entries = []
            
            cases = st.session_state.results
            
            if not cases:
                st.error(" No se encontraron resultados para esta búsqueda.")
            else:
                st.success(f"- Encontrados {len(cases)} expedientes.")
                
                to_process_count = min(max_documents, len(cases))
                
                if not st.session_state.parsed_docs:
                    processed_docs = []
                    status_rows = []
                    progress = st.progress(0)
                    
                    for idx, record in enumerate(cases[:to_process_count]):
                        case_number = record.get("noExpediente", "N/D")
                        decision_date = record.get("fechaFallo", "").split("T")[0] if record.get("fechaFallo") else "Sin fecha"
                        parties = (record.get("involucrados") or "").strip()
                        doc_url = record.get("urlBlob") or ""
                        extracted_text = download_and_extract_pdf(doc_url) if doc_url else "[Sin URL de documento]"
                        
                        if extracted_text.startswith("[ERROR") or extracted_text.startswith("[Sin"):
                            status = " Error"
                            char_count = 0
                            preview_text = extracted_text[:120]
                        else:
                            status = " OK"
                            char_count = len(extracted_text)
                            preview_text = extracted_text[:180] + "…" if len(extracted_text) > 180 else extracted_text
                        
                        status_rows.append({
                            "N°": idx + 1,
                            "Expediente": case_number,
                            "Fecha": decision_date,
                            "Partes": parties[:90] + "…" if len(parties) > 90 else parties,
                            "Caracteres": f"{char_count:,}" if char_count > 0 else "—",
                            "Estado": status,
                            "Vista previa": preview_text
                        })
                        
                        processed_docs.append({
                            "case_number": case_number,
                            "date": decision_date,
                            "parties": parties,
                            "text": extracted_text
                        })
                        
                        progress.progress((idx + 1) / to_process_count)
                    
                    st.session_state.parsed_docs = processed_docs
                    st.session_state.status_entries = status_rows
                
                if st.session_state.status_entries:
                    with st.expander(f" Documentos procesados ({len(st.session_state.status_entries)})", expanded=False):
                        st.dataframe(
                            st.session_state.status_entries,
                            column_config={
                                "N°": st.column_config.NumberColumn("N°", width="small"),
                                "Expediente": st.column_config.TextColumn("Expediente"),
                                "Fecha": st.column_config.TextColumn("Fecha", width="small"),
                                "Partes": st.column_config.TextColumn("Partes"),
                                "Caracteres": st.column_config.TextColumn("Caracteres", width="small"),
                                "Estado": st.column_config.TextColumn("Estado", width="small"),
                                "Vista previa": st.column_config.TextColumn("Vista previa (inicio del texto)", width="large")
                            },
                            hide_index=True,
                            use_container_width=True
                        )
                
                context_parts = []
                for doc in st.session_state.parsed_docs:
                    if not doc['text'].startswith("["):
                        context_parts.append(f"""
<documento expediente="{doc['case_number']}" fecha="{doc['date']}">
Partes: {doc['parties']}
{doc['text'][:10000]}
</documento>
""")
                
                full_context = "\n".join(context_parts)
                st.session_state.context = full_context
                
                successful_docs = sum(1 for d in st.session_state.parsed_docs if not d['text'].startswith("["))
                st.info(f"📚 Contexto cargado: {successful_docs} documentos válidos")

# ─── CHAT INTERFACE ─────────────────────────────────────────────────────────
if 'context' in st.session_state and st.session_state.context:
    st.subheader("- Preguntá sobre los documentos")
    
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
    
    if user_input := st.chat_input("Escribí tu pregunta aquí..."):
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)
        
        with st.chat_message("assistant"):
            with st.spinner("Claude está pensando..."):
                try:
                    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
                    
                    system_prompt = f"""Sos un asistente legal experto en jurisprudencia dominicana.
Tenés acceso a {len(st.session_state.parsed_docs)} sentencias de la Primera Sala de la Suprema Corte de Justicia.
INSTRUCCIONES:
- Respondé basándote ÚNICAMENTE en los documentos proporcionados
- Citá el número de expediente cuando hagas referencia a un caso
- Si la información no está en los documentos, decilo claramente
- Sé conciso pero preciso
DOCUMENTOS:
{st.session_state.context}
"""
                    
                    api_response = client.messages.create(
                        model="claude-3-haiku-20240307",
                        max_tokens=1024,
                        system=system_prompt,
                        messages=[{"role": m["role"], "content": m["content"]} for m in st.session_state.chat_history]
                    )
                    
                    answer = api_response.content[0].text
                    st.markdown(answer)
                    st.session_state.chat_history.append({"role": "assistant", "content": answer})
                
                except Exception as err:
                    st.error(f"Error al consultar a Claude: {str(err)}")

if st.button("Nueva búsqueda (limpiar todo)"):
    st.session_state.clear()
    st.rerun()

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import streamlit as st
from langchain_ollama import OllamaLLM, OllamaEmbeddings
from langchain_chroma import Chroma
from config.prompts import get_adversary_prompt, get_synthesis_prompt

# 1. Configuración de la página
st.set_page_config(
    page_title="Plataforma de Contratación Estatal", 
    layout="centered",
    initial_sidebar_state="collapsed"
)

st.markdown("""
    <style> 
        #MainMenu {visibility: hidden;}
        header {visibility: hidden;}
        .block-container {padding-top: 2rem; padding-bottom: 2rem;}
        .stButton>button {width: 100%; border-radius: 8px; font-weight: 600;}
        .success-box {padding: 1rem; border-radius: 8px; background-color: #1e3a2f; border: 1px solid #2e5a4f; margin-top: 1rem;}
    </style>
""", unsafe_allow_html=True)


# 2. CONEXIÓN RAG (Base de Datos Documental)

@st.cache_resource
def load_system():
    llm = OllamaLLM(model="llama3")
    embeddings = OllamaEmbeddings(model="nomic-embed-text")
    db = Chroma(persist_directory="chroma_db", embedding_function=embeddings)
    retriever = db.as_retriever(search_kwargs={"k": 3})
    return llm, retriever

llm, retriever = load_system()

# ==========================================
# 3. STATE CONTROL
# ==========================================
if "step" not in st.session_state:
    st.session_state.step = "setup" 
if "borrador_usuario" not in st.session_state:
    st.session_state.borrador_usuario = ""
if "pregunta_adversario" not in st.session_state:
    st.session_state.pregunta_adversario = ""
if "texto_final" not in st.session_state:
    st.session_state.texto_final = ""

st.title("Plataforma de Contratación Estatal")
st.markdown("#### Estructuración y Validación Técnica Contractual")
st.markdown("---")

# ==========================================
# PANTALLA 1: ONBOARDING Y CONFIGURACIÓN
# ==========================================
if st.session_state.step == "setup":
    st.info("""
    **Bienvenido a la plataforma de Estructuración Asistida.**
    
    Esta herramienta no redactará los documentos desde cero, sino que elevará el rigor técnico y normativo de su proceso contractual a través de **Síntesis Sinérgica**:
    
    1. **Ideación:** Usted ingresa las ideas base de cada sección.
    2. **Auditoría (Fricción):** El sistema cruzará sus ideas con los manuales de Colombia Compra Eficiente y le exigirá justificar posibles riesgos o vacíos.
    3. **Síntesis:** Una vez resueltos los vacíos, el sistema consolidará sus aportes y redactará la sección con alta precisión técnica y jurídica, lista para sus plantillas oficiales.
    """)
    
    with st.form("contract_setup_form"):
        modalidad = st.selectbox("Modalidad de Selección Normativa", ["Licitación Pública", "Contratación Directa"])
        objeto = st.text_area("Objeto del Contrato", placeholder="Ej: ADQUISICIÓN Y PUESTA EN FUNCIONAMIENTO DE UN ERP...")
        presupuesto = st.number_input("Presupuesto Oficial Estimado (COP)", min_value=0.0, step=1000000.0, format="%f")
        
        if st.form_submit_button("Iniciar Estructuración"):
            if objeto.strip() == "":
                st.error("El objeto del contrato es obligatorio.")
            else:
                st.session_state.modalidad = modalidad
                st.session_state.objeto = objeto
                st.session_state.presupuesto = presupuesto
                st.session_state.step = "ideacion"
                st.rerun()

# ==========================================
# PANTALLA 2: EL FLUJO ESTRUCTURADO (JUSTIFICACIÓN)
# ==========================================
else:
    with st.expander("Ver Parámetros del Contrato Actual", expanded=False):
        st.markdown(f"**Modalidad:** {st.session_state.modalidad} | **Presupuesto:** ${st.session_state.presupuesto:,.0f} COP")
        st.markdown(f"**Objeto:** {st.session_state.objeto}")
        if st.button("Reiniciar Proyecto", key="reset_btn"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

    st.markdown("### Sección 1: Justificación del Contrato")

    # FASE 1: IDEACIÓN (Reemplaza la parte de la creación del prompt con esto)
    if st.session_state.step == "ideacion":
        st.markdown("Por favor, describa brevemente la necesidad que motiva esta contratación. ¿Por qué el Fondo Rotatorio necesita esto?")
        borrador = st.text_area("Su idea base:", height=150)
        
        if st.button("Someter a Auditoría Técnica"):
            if borrador.strip() == "":
                st.warning("Debe ingresar una idea base para continuar.")
            else:
                st.session_state.borrador_usuario = borrador
                st.session_state.step = "friccion"
                
                with st.spinner("Analizando normatividad y evaluando riesgos lógicos..."):
                    docs = retriever.invoke(borrador + " " + st.session_state.modalidad)
                    contexto_normativo = "\n\n".join([doc.page_content for doc in docs])
                    
                    # AQUÍ USAMOS LA FUNCIÓN IMPORTADA
                    prompt_adversario = get_adversary_prompt(
                        st.session_state.modalidad, 
                        st.session_state.objeto, 
                        borrador, 
                        contexto_normativo
                    )
                    st.session_state.pregunta_adversario = llm.invoke(prompt_adversario)
                st.rerun()

    # FASE 2: FRICCIÓN (Reemplaza la parte de la síntesis con esto)
    elif st.session_state.step == "friccion":
        # Mostrar la pregunta del auditor
        st.markdown("**Observación del Auditor Técnico:**")
        st.info(st.session_state.pregunta_adversario)
        
        # Campo para que el usuario ingrese su defensa
        defensa = st.text_area(
            "Escriba su justificación o respuesta a la observación:",
            height=150,
            key="defensa_input"
        )
    
    # Botón para consolidar
    if st.button("Consolidar y Generar Redacción Final"):
        if defensa.strip() == "":
            st.warning("Debe responder a la observación del auditor.")
        else:
            # Guardar defensa en sesión (opcional, pero útil para persistencia)
            st.session_state.defensa_usuario = defensa
            st.session_state.step = "sintesis"
            
            with st.spinner("Sintetizando aportes y redactando documento formal..."):
                prompt_sintesis = get_synthesis_prompt(
                    st.session_state.objeto,
                    st.session_state.borrador_usuario,
                    defensa  # o st.session_state.defensa_usuario
                )
                st.session_state.texto_final = llm.invoke(prompt_sintesis)
            st.rerun()

    # FASE 3: SÍNTESIS (LA RECOMPENSA)
    elif st.session_state.step == "sintesis":
        st.success("Auditoría superada. El sistema ha consolidado sus aportes en una redacción técnica final.")
        st.markdown(f'<div class="success-box">{st.session_state.texto_final}</div>', unsafe_allow_html=True)
        
        st.markdown("---")
        if st.button("Aprobar y pasar a la siguiente sección (Ej: Especificaciones Técnicas)"):
            st.info("Funcionalidad en desarrollo: Aquí el sistema avanzaría al siguiente apartado de su plantilla.")
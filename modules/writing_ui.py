import streamlit as st
import random
import datetime
import pandas as pd
from core.data_manager import get_session_db, add_writing_entry, get_writing_log
from core.localization import get_text

def count_stats(text):
    """Calcula estatísticas do texto: palavras, caracteres e parágrafos."""
    words = len(text.split())
    chars = len(text)
    paragraphs = len([p for p in text.split('\n') if p.strip()])
    return words, chars, paragraphs

def writing_ui(language, debug_mode):
    """
    Renderiza a página do Modo de Escrita, com depuração e interface traduzida.
    """
    if st.button(get_text("back_to_dashboard", language), key="back_from_writing"):
        st.session_state.current_page = "Homepage"
        st.rerun()

    st.header(get_text("writing_mode_button", language))
    
    db_df = get_session_db(language)
    palavras_ativas = sorted(db_df[db_df['ativa']]['palavra'].tolist())

    if debug_mode:
        st.subheader(f"Modo de Depuração Detalhado ({get_text('writing_mode_button', language)})")
        st.write("---")
        st.markdown(f"**1. Dados de Entrada:**")
        st.write(f"- Total de palavras ativas encontradas: `{len(palavras_ativas)}`")
        with st.expander("Ver lista de palavras ativas"):
            st.write(palavras_ativas)
        st.divider()

    if not palavras_ativas:
        st.warning(get_text("no_active_words", language))
        return

    st.info(get_text("writing_info", language))

    writing_log = get_writing_log(language)
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        if 'selected_word_index' not in st.session_state or st.session_state.selected_word_index >= len(palavras_ativas):
            st.session_state.selected_word_index = 0

        selected_index = st.selectbox(
            get_text("choose_word_label", language),
            index=st.session_state.selected_word_index,
            options=range(len(palavras_ativas)),
            format_func=lambda x: palavras_ativas[x],
            key='word_selector'
        )
        
        if st.session_state.selected_word_index != selected_index:
            st.session_state.selected_word_index = selected_index
            st.session_state.word_for_text_area = None 
            st.rerun()

    with col2:
        st.write("") 
        st.write("")
        if st.button(get_text("random_word_button", language), use_container_width=True):
            new_index = random.choice(range(len(palavras_ativas)))
            if new_index != st.session_state.selected_word_index:
                st.session_state.selected_word_index = new_index
                st.session_state.word_for_text_area = None
                st.rerun()

    palavra_atual = palavras_ativas[st.session_state.selected_word_index]
    st.markdown(f"### {get_text('practicing_with', language)} <span class='keyword-highlight'>{palavra_atual}</span>", unsafe_allow_html=True)

    if st.session_state.get('word_for_text_area') != palavra_atual:
        texto_anterior = ""
        if writing_log:
            log_df = pd.DataFrame(writing_log)
            if not log_df.empty:
                palavra_entries = log_df[log_df['palavra'] == palavra_atual]
                if not palavra_entries.empty:
                    latest_entry = palavra_entries.sort_values(by='data_escrita', ascending=False).iloc[0]
                    texto_anterior = latest_entry['texto']
        
        st.session_state.text_area_content = texto_anterior
        st.session_state.word_for_text_area = palavra_atual

    texto_digitado = st.text_area(
        get_text("text_area_label", language), 
        height=300, 
        key="text_area_content"
    )

    word_count, char_count, paragraph_count = count_stats(texto_digitado)
    
    col_stats1, col_stats2, col_stats3 = st.columns(3)
    col_stats1.metric(get_text("words_metric", language), f"{word_count}")
    col_stats2.metric(get_text("chars_metric", language), f"{char_count}")
    col_stats3.metric(get_text("paragraphs_metric", language), f"{paragraph_count}")

    if st.button(get_text("save_text_button", language), type="primary"):
        if not texto_digitado.strip():
            st.error(get_text("empty_text_error", language))
        else:
            entry = {
                "palavra": palavra_atual,
                "texto": texto_digitado,
                "data_escrita": datetime.datetime.now().isoformat(),
                "word_count": word_count,
                "char_count": char_count,
                "paragraph_count": paragraph_count
            }
            add_writing_entry(entry, language)
            st.success(get_text("text_saved_success", language).format(word=palavra_atual))
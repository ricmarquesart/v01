import streamlit as st
import pandas as pd
import random
import datetime
import altair as alt
from collections import defaultdict
from core.data_manager import load_sentence_data, load_sentence_log, save_sentence_log, delete_sentence_log_entry
from core.localization import get_text

def count_stats(text):
    """Calcula estatísticas do texto: palavras, caracteres e parágrafos."""
    words = len(text.split())
    chars = len(text)
    paragraphs = len([p for p in text.split('\n') if p.strip()])
    return words, chars, paragraphs

def format_sentences_to_txt(log_data, words_data, include_comments=True, include_corrections=True, include_grades=True, correction_status='Todas'):
    """Formata os dados do log de frases para uma string de texto com base nos filtros."""
    output_string = ""
    for entry in log_data:
        palavra_chave_unica = entry['palavra_chave']
        dados_palavra = words_data.get(palavra_chave_unica, {})
        palavra_base = dados_palavra.get('palavra_base', palavra_chave_unica)
        
        frases_formatadas = []
        notas_validas = []
        
        if 'frases' in entry and isinstance(entry['frases'], list):
            for i, frase_info in enumerate(entry['frases']):
                if isinstance(frase_info, dict) and frase_info.get('frase'):
                    
                    corrigido = frase_info.get('corrigido', False)
                    
                    if (correction_status == 'Corrigidas' and not corrigido) or \
                       (correction_status == 'Não Corrigidas' and corrigido):
                        continue

                    frase_str = f"{i+1}- {frase_info['frase']}"
                    
                    if include_comments and frase_info.get('comentario'):
                        frase_str += f"\n   Comentário: {frase_info['comentario']}"
                    if include_corrections and frase_info.get('correcao'):
                        frase_str += f"\n   Correção: {frase_info['correcao']}"
                    
                    nota = frase_info.get('nota')
                    if isinstance(nota, (int, float)):
                        notas_validas.append(nota)
                        if include_grades:
                            frase_str += f"\n   Nota: {nota}"
                            
                    frases_formatadas.append(frase_str)
        
        if frases_formatadas:
            media_geral = sum(notas_validas) / len(notas_validas) if notas_validas else 0.0
            media_str = f" - Média: {media_geral:.1f}/10" if include_grades and notas_validas else ""
            
            output_string += f"Palavra: {palavra_base} ({dados_palavra.get('Classe', 'N/A')}){media_str}\n"
            output_string += "\n".join(frases_formatadas)
            output_string += "\n\n"
            
    return output_string

def sentence_writing_ui(language, debug_mode):
    st.header(f"{get_text('sentence_writing_title', language)}")

    if st.button(get_text("back_to_dashboard", language), key="back_from_sentence_writing"):
        st.session_state.current_page = "Homepage"
        if 'word_sentence_index' in st.session_state:
            del st.session_state['word_sentence_index']
        st.rerun()

    words_data = load_sentence_data(language)
    sentence_log = load_sentence_log(language)
    log_df = pd.DataFrame(sentence_log)

    palavras_do_log = list(log_df['palavra_chave'].unique()) if not log_df.empty and 'palavra_chave' in log_df.columns else []
    todas_as_palavras_set = set(list(words_data.keys())) | set(palavras_do_log)
    lista_palavras_total = sorted(list(todas_as_palavras_set))

    if not lista_palavras_total:
        st.warning(get_text('no_sentence_words_found', language))
        return

    # --- Estatísticas ---
    total_palavras = len(lista_palavras_total)
    completas = 0
    parciais = {i: 0 for i in range(1, 5)}

    if not log_df.empty and 'palavra_chave' in log_df.columns:
        for word_key in lista_palavras_total:
            entradas = log_df[log_df['palavra_chave'] == word_key]
            if not entradas.empty:
                num_frases = 0
                frases_data = entradas.iloc[0].get('frases', [])
                if isinstance(frases_data, list):
                    num_frases = len([f['frase'] for f in frases_data if f.get('frase','').strip()])

                if num_frases >= 5:
                    completas += 1
                elif 1 <= num_frases <= 4:
                    parciais[num_frases] += 1
    
    total_parciais = sum(parciais.values())

    st.subheader(get_text('stats_header', language))
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric(get_text('total_words_metric_sentence', language), total_palavras)
    kpi2.metric(get_text('completed_words_metric', language), completas)
    kpi3.metric(get_text('partial_words_metric', language), total_parciais)
    kpi4.metric(get_text('untouched_words_metric', language), total_palavras - completas - total_parciais)

    # --- Filtros e Seleção ---
    st.subheader(get_text('word_selection_header', language))
    
    niveis = sorted(list(set(d.get('Nível', 'N/A') for d in words_data.values())))
    classes = sorted(list(set(d.get('Classe', 'N/A') for d in words_data.values())))
    
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        filtro_status = st.selectbox(get_text('filter_by_status', language), 
                                     ["Todas", "Completas (5)", "Parciais (1-4)", "Intocadas (0)",
                                      "4 frases", "3 frases", "2 frases", "1 frase"])
    with col_f2:
        filtro_nivel = st.selectbox(get_text('filter_by_level', language), ["Todos"] + niveis)
    with col_f3:
        filtro_classe = st.selectbox(get_text('filter_by_class', language), ["Todos"] + classes)

    palavras_filtradas = []
    for word_key in lista_palavras_total:
        num_frases = 0
        if not log_df.empty and 'palavra_chave' in log_df.columns:
            entradas = log_df[log_df['palavra_chave'] == word_key]
            if not entradas.empty:
                frases_data = entradas.iloc[0].get('frases', [])
                if isinstance(frases_data, list):
                    num_frases = len([f['frase'] for f in frases_data if f.get('frase','').strip()])
        
        status_ok = (filtro_status == "Todas") or \
                    (filtro_status == "Completas (5)" and num_frases >= 5) or \
                    (filtro_status == "Parciais (1-4)" and 1 <= num_frases <= 4) or \
                    (filtro_status == "Intocadas (0)" and num_frases == 0) or \
                    (filtro_status.startswith(str(num_frases)))

        dados_palavra = words_data.get(word_key, {})
        nivel_ok = (filtro_nivel == "Todos") or (dados_palavra.get('Nível') == filtro_nivel)
        classe_ok = (filtro_classe == "Todos") or (dados_palavra.get('Classe') == filtro_classe)

        if status_ok and nivel_ok and classe_ok:
            palavras_filtradas.append(word_key)

    if not palavras_filtradas:
        st.warning(get_text('no_words_in_filter', language))
        return

    # Garante que o índice esteja sempre dentro dos limites da lista filtrada
    if 'word_sentence_index' not in st.session_state or st.session_state.word_sentence_index >= len(palavras_filtradas):
        st.session_state.word_sentence_index = random.randint(0, len(palavras_filtradas) - 1)
    
    col1, col2 = st.columns([3, 1])
    with col1:
        selected_idx = st.selectbox(
            get_text('choose_word_sentence', language), 
            options=range(len(palavras_filtradas)),
            format_func=lambda x: f"{palavras_filtradas[x]}",
            index=st.session_state.word_sentence_index,
            key='selectbox_palavra'
        )
        if selected_idx != st.session_state.word_sentence_index:
            st.session_state.word_sentence_index = selected_idx
            st.rerun()

    with col2:
        st.write("")
        st.write("")
        if st.button(get_text("random_word_button", language), use_container_width=True):
            st.session_state.word_sentence_index = random.randint(0, len(palavras_filtradas) - 1)
            st.rerun()

    palavra_em_foco_key = palavras_filtradas[st.session_state.word_sentence_index]
    palavra_info = words_data.get(palavra_em_foco_key, {})

    notas = []
    if not log_df.empty and 'palavra_chave' in log_df.columns:
        entradas = log_df[log_df['palavra_chave'] == palavra_em_foco_key]
        if not entradas.empty:
            frases_data = entradas.iloc[0].get('frases', [])
            if isinstance(frases_data, list):
                for f in frases_data:
                    if isinstance(f.get('nota'), (int, float)):
                        notas.append(f['nota'])

    media_geral = sum(notas) / len(notas) if notas else 0.0

    st.markdown("---")
    st.markdown(f"<h1 style='text-align: center; color: #D32F2F;'>{palavra_info.get('palavra_base', palavra_em_foco_key)} - {get_text('average_grade_label', language)}: {media_geral:.1f}/10</h1>", unsafe_allow_html=True)
    st.markdown(f"<p style='text-align: center;'><strong>{get_text('class_level_label', language)}:</strong> {palavra_info.get('Classe', 'N/A')} | <strong>Nível:</strong> {palavra_info.get('Nível', 'N/A')}</p>", unsafe_allow_html=True)
    st.info(f"**{get_text('reference_sentence_label', language)}:** \"{palavra_info.get('Outra Frase', 'N/A')}\"")
    st.markdown("---")
    
    log_existente = None
    if not log_df.empty and 'palavra_chave' in log_df.columns:
        entradas = log_df[log_df['palavra_chave'] == palavra_em_foco_key]
        if not entradas.empty:
            log_existente = entradas.iloc[0].to_dict()

    if log_existente is None:
        log_existente = {'palavra_chave': palavra_em_foco_key, 'frases': [{'frase': '', 'comentario': '', 'data': None, 'corrigido': False, 'nota': 0, 'correcao': ''} for _ in range(5)]}

    frases_comentarios = log_existente.get('frases', [{'frase': '', 'comentario': ''} for _ in range(5)])
    while len(frases_comentarios) < 5:
        frases_comentarios.append({'frase': '', 'comentario': ''})

    novas_frases_comentarios = []
    
    st.subheader(get_text('your_sentences_header', language))
    for i in range(5):
        col_frase, col_comentario = st.columns(2)
        frase_atual = frases_comentarios[i].get('frase', '')
        comentario_atual = frases_comentarios[i].get('comentario', '')
        corrigido_atual = frases_comentarios[i].get('corrigido', False)
        nota_atual = frases_comentarios[i].get('nota', 0)
        correcao_atual = frases_comentarios[i].get('correcao', '')

        with col_frase:
            frase_input = st.text_area(f"Frase {i+1}", value=frase_atual, key=f"frase_{palavra_em_foco_key}_{i}", height=100)
        with col_comentario:
            comentario_input = st.text_area(f"Comentário {i+1}", value=comentario_atual, key=f"comentario_{palavra_em_foco_key}_{i}", placeholder=get_text('feedback_placeholder', language), height=100)

        col_sub1, col_sub2, col_sub3 = st.columns([3,1,1])
        with col_sub1:
            correcao_input = st.text_input(get_text('correction_label', language), value=correcao_atual, key=f"correcao_{palavra_em_foco_key}_{i}")
        with col_sub2:
            nota_input = st.number_input(get_text('grade_label', language), min_value=0, max_value=10, value=nota_atual, key=f"nota_{palavra_em_foco_key}_{i}")
        with col_sub3:
            st.write("")
            st.write("")
            corrigido_input = st.checkbox(get_text('corrected_checkbox', language), value=corrigido_atual, key=f"corrigido_{palavra_em_foco_key}_{i}")

        word_count, char_count, p_count = count_stats(frase_input)
        st.markdown(f"<small>{get_text('words_metric', language)}: {word_count} | {get_text('chars_metric', language)}: {char_count} | {get_text('paragraphs_metric', language)}: {p_count}</small>", unsafe_allow_html=True)
        st.markdown("<hr style='margin-top: 1rem; margin-bottom: 1rem;'>", unsafe_allow_html=True)
            
        data_modificacao = frases_comentarios[i].get('data')
        if frase_input != frase_atual or comentario_input != comentario_atual or corrigido_input != corrigido_atual or nota_input != nota_atual or correcao_input != correcao_atual:
            if frase_input.strip() or comentario_input.strip() or correcao_input.strip():
                data_modificacao = datetime.datetime.now().isoformat()
            
        novas_frases_comentarios.append({'frase': frase_input, 'comentario': comentario_input, 'data': data_modificacao, 'corrigido': corrigido_input, 'nota': nota_input, 'correcao': correcao_input})

    col_save, col_delete = st.columns(2)
    with col_save:
        if st.button(get_text('save_button_sentence', language), use_container_width=True, type="primary"):
            nova_entrada = {
                'palavra_chave': palavra_em_foco_key,
                'frases': [item for item in novas_frases_comentarios if item['frase'].strip() or item['comentario'].strip() or item['correcao'].strip()]
            }
            
            log_encontrado_idx = -1
            for idx, entry in enumerate(sentence_log):
                if entry['palavra_chave'] == palavra_em_foco_key:
                    log_encontrado_idx = idx
                    break
            
            if log_encontrado_idx != -1:
                sentence_log[log_encontrado_idx] = nova_entrada
            else:
                sentence_log.append(nova_entrada)
            
            save_sentence_log(sentence_log, language)
            st.success(get_text('save_success_sentence', language).format(word=palavra_em_foco_key))
            st.rerun()
            
    with col_delete:
        if log_existente and any(f.get('frase', '').strip() for f in log_existente.get('frases', [])):
            if st.button(get_text("delete_word_data_button", language), use_container_width=True):
                delete_sentence_log_entry(palavra_em_foco_key, language)
                st.success(get_text("delete_word_data_success", language).format(word=palavra_em_foco_key))
                if 'word_sentence_index' in st.session_state:
                    del st.session_state['word_sentence_index']
                st.rerun()

    with st.expander(get_text('export_options_header', language)):
        col_export1, col_export2, col_export3 = st.columns(3)
        with col_export1:
            incluir_comentarios = st.toggle(get_text('include_comments_toggle', language), True)
        with col_export2:
            incluir_correcoes = st.toggle(get_text('include_corrections_toggle', language), True)
        with col_export3:
            incluir_notas = st.toggle(get_text('include_grades_toggle', language), True)

        filtro_correcao = st.radio(
            get_text('filter_by_correction_label', language), 
            [get_text('all_sentences', language), 
             get_text('corrected_sentences', language), 
             get_text('not_corrected_sentences', language)],
            horizontal=True
        )
        
        map_filtro = {
            get_text('all_sentences', language): "Todas",
            get_text('corrected_sentences', language): "Corrigidas",
            get_text('not_corrected_sentences', language): "Não Corrigidas"
        }
        
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            txt_all = format_sentences_to_txt(sentence_log, words_data, incluir_comentarios, incluir_correcoes, incluir_notas, map_filtro[filtro_correcao])
            st.download_button(
                label=get_text('export_all_button', language),
                data=txt_all.encode('utf-8'),
                file_name='todas_as_frases.txt',
                mime='text/plain',
                use_container_width=True
            )
        with col_btn2:
            log_filtrado_export = [entry for entry in sentence_log if entry['palavra_chave'] in palavras_filtradas]
            txt_filtered = format_sentences_to_txt(log_filtrado_export, words_data, incluir_comentarios, incluir_correcoes, incluir_notas, map_filtro[filtro_correcao])
            st.download_button(
                label=get_text('export_filtered_button', language),
                data=txt_filtered.encode('utf-8'),
                file_name=f'frases_filtradas.txt',
                mime='text/plain',
                use_container_width=True,
                key='download_filtered'
            )
    
    st.markdown("---")
    st.subheader(get_text("activity_chart_header", language))
    
    datas_frases = []
    if not log_df.empty and 'frases' in log_df.columns:
        for _, row in log_df.iterrows():
            if isinstance(row['frases'], list):
                for item in row['frases']:
                    if isinstance(item, dict) and item.get('data'):
                        datas_frases.append(item['data'])

    if datas_frases:
        df_datas = pd.DataFrame(datas_frases, columns=['data'])
        df_datas['data'] = pd.to_datetime(df_datas['data']).dt.date
        
        today = datetime.date.today()
        last_30_days = today - datetime.timedelta(days=30)
        df_ultimos_30_dias = df_datas[df_datas['data'] >= last_30_days]
        
        contagem_diaria = df_ultimos_30_dias['data'].value_counts().sort_index().reset_index()
        contagem_diaria.columns = ['Data', 'Contagem']
        
        chart = alt.Chart(contagem_diaria).mark_bar().encode(
            x=alt.X('Data:T', title='Data'),
            y=alt.Y('Contagem:Q', title='Nº de Frases'),
            tooltip=['Data:T', 'Contagem:Q']
        ).properties(
            title=get_text("last_30_days_activity_title", language)
        )
        st.altair_chart(chart, use_container_width=True)
    else:
        st.info(get_text("no_activity_data", language))
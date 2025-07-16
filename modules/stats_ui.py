import streamlit as st
import pandas as pd
from collections import Counter
import datetime
from core.data_manager import (
    get_history, get_session_db, save_vocab_db, get_writing_log,
    clear_history, get_performance_summary, load_and_cache_data,
    delete_writing_entries, delete_cloze_exercises, TIPOS_EXERCICIO_ANKI,
    get_exercise_id_to_type_map
)
from core.localization import get_text

def estatisticas_ui(language):
    """
    Renderiza a página de Estatísticas e Gerenciador de Vocabulário, com depuração e tradução.
    """
    if st.button(get_text("back_to_dashboard", language), key="back_from_stats"):
        st.session_state.current_page = "Homepage"
        st.rerun()

    st.header(get_text("stats_button", language))

    db_df = get_session_db(language)
    summary = get_performance_summary(language)

    # --- KPIs ---
    st.subheader(get_text("db_summary_header", language))
    kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
    kpi1.metric(get_text("total_words_metric", language), summary['db_kpis']['total'])
    kpi2.metric(get_text("active_words_metric", language), summary['db_kpis']['ativas'])
    kpi3.metric(get_text("inactive_words_metric", language), summary['db_kpis']['inativas'])
    kpi4.metric(get_text("anki_source_metric", language), summary['db_kpis']['anki'])
    kpi5.metric(get_text("gpt_source_metric", language), summary['db_kpis']['gpt'])

    parsing_errors = st.session_state.get(f'parsing_errors_{language}', [])
    if parsing_errors:
        with st.expander(get_text("import_log_header", language)):
            st.warning(get_text("import_log_warning", language))
            for error in parsing_errors:
                st.code(error, language='text')

    st.divider()
    st.subheader(get_text("vocab_manager_header", language))

    col_f1, col_f2, col_f3 = st.columns([2, 3, 2])
    with col_f1:
        fontes_disponiveis = ["Todas"]
        if 'fonte' in db_df.columns and not db_df['fonte'].empty:
            fontes_disponiveis.extend(list(db_df['fonte'].unique()))
        fonte_selecionada = st.selectbox(get_text("filter_by_source", language), fontes_disponiveis)

    with col_f2:
        if 'data_adicao' in db_df.columns and not db_df['data_adicao'].isnull().all():
            try:
                db_df['data_adicao_dt'] = pd.to_datetime(db_df['data_adicao'])
                data_min = db_df['data_adicao_dt'].min().date()
                data_max = db_df['data_adicao_dt'].max().date()
                data_selecionada = st.date_input(get_text("filter_by_date", language), value=(data_min, data_max), min_value=data_min, max_value=data_max)
            except Exception:
                data_selecionada = (datetime.date.today(), datetime.date.today())
        else:
            data_selecionada = (datetime.date.today(), datetime.date.today())

    df_filtrado = db_df.copy()
    if fonte_selecionada != "Todas":
        df_filtrado = df_filtrado[df_filtrado['fonte'] == fonte_selecionada]
    if 'data_adicao_dt' in df_filtrado.columns and len(data_selecionada) == 2:
        start_date = pd.to_datetime(data_selecionada[0])
        end_date = pd.to_datetime(data_selecionada[1]) + pd.Timedelta(days=1)
        df_filtrado = df_filtrado[(df_filtrado['data_adicao_dt'] >= start_date) & (df_filtrado['data_adicao_dt'] < end_date)]

    with col_f3:
        st.write("")
        if st.button(get_text("delete_filtered_button", language), type="primary", use_container_width=True):
            if not df_filtrado.empty:
                indices_para_deletar = df_filtrado.index
                db_df_original = get_session_db(language)
                db_df_original.drop(indices_para_deletar, inplace=True)
                save_vocab_db(db_df_original, language)
                st.session_state[f"db_df_{language}"] = db_df_original
                st.error(f"{len(df_filtrado)} palavras filtradas foram deletadas!")
                st.rerun()
            else:
                st.info("Não há palavras na seleção filtrada para deletar.")

    df_filtrado = df_filtrado.sort_values(by='palavra', ascending=True).reset_index(drop=True)

    def calcular_progresso_geral(row):
        progresso_dict = row.get('progresso', {})
        if not isinstance(progresso_dict, dict) or not progresso_dict: return 0
        acertos_count = list(progresso_dict.values()).count('acerto')
        total_exercicios = len(progresso_dict)
        return (acertos_count / total_exercicios * 100) if total_exercicios > 0 else 0

    df_filtrado['progresso_percent'] = df_filtrado.apply(calcular_progresso_geral, axis=1)

    if 'mastery_count' not in df_filtrado.columns:
        df_filtrado['mastery_count'] = 0
    df_filtrado['mastery_count'] = df_filtrado['mastery_count'].fillna(0).astype(int)
    df_filtrado['mestria'] = df_filtrado['mastery_count'].apply(lambda x: "🏆" * x)
    df_filtrado['deletar'] = False

    mostrar_detalhes = st.checkbox(get_text("show_exercise_details", language))

    colunas_visiveis = ['ativa', 'deletar', 'palavra', 'fonte', 'progresso_percent', 'mestria']
    column_config = {
        "ativa": st.column_config.CheckboxColumn(get_text("col_active", language), width="small"),
        "deletar": st.column_config.CheckboxColumn(get_text("col_delete", language), width="small"),
        "palavra": st.column_config.TextColumn(get_text("col_word", language), width="large", disabled=True),
        "fonte": st.column_config.TextColumn(get_text("col_source", language), disabled=True),
        "progresso_percent": st.column_config.ProgressColumn(get_text("col_progress", language), format="%.0f%%", min_value=0, max_value=100),
        "mestria": st.column_config.TextColumn(get_text("col_status", language), help=get_text("col_status_help", language)),
    }

    if mostrar_detalhes:
        id_para_tipo = get_exercise_id_to_type_map(language)
        todos_os_tipos = sorted(list(set(id_para_tipo.values())))
        
        for tipo_ex in todos_os_tipos:
            if tipo_ex == '7-Cloze-Text': continue
            col_name = f"ex_{tipo_ex.replace(' ', '_')}"
            
            def calcular_progresso_por_tipo(row, tipo_alvo):
                progresso_dict = row.get('progresso', {})
                exercicios_do_tipo = [status for id_ex, status in progresso_dict.items() if id_para_tipo.get(id_ex) == tipo_alvo]
                if not exercicios_do_tipo:
                    return None
                
                acertos = exercicios_do_tipo.count('acerto')
                return (acertos / len(exercicios_do_tipo)) * 100

            df_filtrado[col_name] = df_filtrado.apply(calcular_progresso_por_tipo, args=(tipo_ex,), axis=1)
            colunas_visiveis.append(col_name)
            column_config[col_name] = st.column_config.ProgressColumn(
                tipo_ex, 
                format="%.0f%%", 
                min_value=0, 
                max_value=100
            )

    df_editado = st.data_editor(df_filtrado[colunas_visiveis], column_config=column_config, use_container_width=True, hide_index=True, key="word_manager")

    col_b1, col_b2 = st.columns(2)
    with col_b1:
        if st.button(get_text("save_active_status_button", language), use_container_width=True):
            update_map = df_editado.set_index('palavra')['ativa']
            db_df_original = get_session_db(language)
            db_df_original['ativa'] = db_df_original['palavra'].map(update_map).fillna(db_df_original['ativa'])
            save_vocab_db(db_df_original, language)
            st.session_state[f"db_df_{language}"] = db_df_original
            st.success("Status de ativação salvo!")
            st.rerun()
            
    with col_b2:
        if st.button(get_text("delete_selected_button", language), use_container_width=True):
            palavras_para_deletar = df_editado[df_editado['deletar']]['palavra']
            if not palavras_para_deletar.empty:
                db_df_original = get_session_db(language)
                indices_para_deletar = db_df_original[db_df_original['palavra'].isin(palavras_para_deletar)].index
                db_df_original.drop(indices_para_deletar, inplace=True)
                save_vocab_db(db_df_original, language)
                st.session_state[f"db_df_{language}"] = db_df_original
                st.warning(f"{len(indices_para_deletar)} palavras selecionadas foram deletadas!")
                st.rerun()
            else:
                st.info("Nenhuma palavra foi marcada para deleção.")

    st.divider()
    st.subheader(get_text("written_texts_log_header", language))
    writing_log = get_writing_log(language)
    if not writing_log:
        st.info("Você ainda não salvou nenhum texto no 'Modo de Escrita'.")
    else:
        df_log = pd.DataFrame(writing_log)
        df_log['data_escrita'] = pd.to_datetime(df_log['data_escrita']).dt.strftime('%d/%m/%Y %H:%M')
        df_log['Deletar'] = False
        df_log = df_log[['Deletar', 'palavra', 'data_escrita', 'texto']]
        edited_log_df = st.data_editor(df_log, column_config={"Deletar": st.column_config.CheckboxColumn(required=True), "palavra": st.column_config.TextColumn("Palavra", disabled=True), "data_escrita": st.column_config.TextColumn("Data", disabled=True), "texto": st.column_config.TextColumn("Texto", disabled=True)}, use_container_width=True, hide_index=True, key="writing_log_editor")
        if st.button("Deletar Textos Escritos Selecionados", type="primary"):
            entries_to_delete_df = edited_log_df[edited_log_df['Deletar']]
            if not entries_to_delete_df.empty:
                original_log_records = df_log.to_dict('records')
                entries_to_delete_list = [original_log_records[i] for i in entries_to_delete_df.index]
                final_list_to_delete = []
                for record_to_delete in entries_to_delete_list:
                    for original_entry in writing_log:
                        if (original_entry['palavra'] == record_to_delete['palavra'] and original_entry['texto'] == record_to_delete['texto'] and pd.to_datetime(original_entry['data_escrita']).strftime('%d/%m/%Y %H:%M') == record_to_delete['data_escrita']):
                            final_list_to_delete.append(original_entry)
                            break
                if final_list_to_delete:
                    delete_writing_entries(final_list_to_delete, language)
                    st.success(f"{len(final_list_to_delete)} texto(s) deletado(s) com sucesso!")
                    st.rerun()
            else:
                st.info("Nenhum texto foi marcado para deleção.")

    st.divider()
    st.subheader(get_text("cloze_texts_manager_header", language))
    _, gpt_exercicios_cloze = load_and_cache_data(language)
    cloze_exercises = [ex for ex in gpt_exercicios_cloze if ex.get('tipo') == '7-Cloze-Text']
    if not cloze_exercises:
        st.info(get_text("no_cloze_in_memory", language))
    else:
        cloze_data_for_df = []
        for ex in cloze_exercises:
            cloze_data_for_df.append({"Deletar": False, "Nome": ex.get("titulo", "Título não encontrado"), "Nível": ex.get("cefr_level", "N/A"), "original_exercise": ex})
        df_cloze = pd.DataFrame(cloze_data_for_df)
        edited_cloze_df = st.data_editor(df_cloze[['Deletar', 'Nome', 'Nível']], column_config={"Deletar": st.column_config.CheckboxColumn(required=True), "Nome": st.column_config.TextColumn("Título do Texto", disabled=True, help="O título do exercício de cloze."), "Nível": st.column_config.TextColumn("Nível", disabled=True)}, use_container_width=True, hide_index=True, key="cloze_manager_editor")
        if st.button(get_text("delete_cloze_button", language), type="primary"):
            to_delete_df = edited_cloze_df[edited_cloze_df['Deletar']]
            if not to_delete_df.empty:
                indices_to_delete = to_delete_df.index
                exercises_to_delete_list = [df_cloze.loc[i, 'original_exercise'] for i in indices_to_delete]
                delete_cloze_exercises(exercises_to_delete_list, language)
                st.success(f"{len(exercises_to_delete_list)} texto(s) de Cloze deletado(s) com sucesso!")
                st.cache_data.clear()
                st.rerun()
            else:
                st.info("Nenhum texto foi marcado para deleção.")

    st.divider()
    st.subheader(get_text("danger_zone_header", language))
    st.warning(get_text("danger_zone_warning", language))
    if st.button(get_text("clear_history_button", language), type="primary"):
        clear_history(language)
        st.rerun()
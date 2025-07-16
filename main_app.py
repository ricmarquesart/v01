import streamlit as st
import pandas as pd
import altair as alt
from collections import Counter
from core.data_manager import load_and_cache_data, get_performance_summary
from core.localization import get_text

# --- Configuração da Página e CSS ---
st.set_page_config(page_title="CELPIP & TCF Study App", layout="centered")

# CORREÇÃO: Reintroduz as regras de estilo para o destaque e tamanho da fonte
st.markdown("""
    <style>
    .block-container { max-width: 1100px; }
    .main-title { text-align: center; font-weight: bold; font-size: 48px; margin-bottom: 20px; }
    .section-header { text-align: center; font-weight: bold; font-size: 28px; margin-top: 40px; margin-bottom: 15px; }
    .stButton>button { height: 100px; font-size: 20px; font-weight: bold; border-radius: 10px; }
    .quiz-title { font-size: 38px; font-weight: bold; margin-bottom: 5px; }
    .question-bg { font-size: 27px; padding: 1.5rem; border-radius: 0.75rem; line-height: 1.4; margin-bottom: 0.5rem; }
    .options-container { overflow-y: auto; padding: 1rem; border-radius: 0.75rem; margin-bottom: 0.5rem; }
    
    .keyword-highlight { 
        font-weight: bold !important; 
    }

    /* --- Estilos do Tema Claro --- */
    [data-theme="light"] .section-header { color: #005A9C; }
    [data-theme="light"] .question-bg { background-color: #eef1f5 !important; border-color: #d6dae0 !important; }
    [data-theme="light"] .options-container { border: 1px solid #d6dae0; }
    [data-theme="light"] .keyword-highlight, [data-theme="light"] .keyword-highlight span {
        color: #D32F2F !important; /* Vermelho escuro */
    }
    [data-theme="light"] .stButton>button {
        background-color: #f0f2f6;
        border: 1px solid #d6dae0;
        color: #31333f;
    }

    /* --- Estilos do Tema Escuro --- */
    [data-theme="dark"] .section-header { color: #89cff0; }
    [data-theme="dark"] .question-bg { background-color: #1E1E1E !important; border: 1px solid #3c3c3c !important; }
    [data-theme="dark"] .options-container { border: 1px solid #3c3c3c; }
    [data-theme="dark"] .stButton>button { background-color: #2a2a2a; border: 1px solid #4a4a4a; }
    [data-theme="dark"] .keyword-highlight, [data-theme="dark"] .keyword-highlight span {
        color: #FFD700 !important; /* Amarelo (Dourado) */
    }
    </style>
""", unsafe_allow_html=True)

def inject_language_specific_css(language):
    """Aplica o CSS de fundo específico para cada idioma e tema."""
    color_en_light = "#FFF0F0"
    color_fr_light = "#F0F8FF"
    color_dark = "#121212"

    css = f"""
    <style>
        [data-theme="light"] .stApp {{
            background-color: {color_en_light if language == 'en' else color_fr_light};
        }}
        [data-theme="dark"] .stApp {{
            background-color: {color_dark};
        }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

def render_homepage(language, debug_mode):
    st.markdown(f"<h1 class='main-title'>{get_text('dashboard_title', language)}</h1>", unsafe_allow_html=True)
    if debug_mode:
        st.warning("Modo de Depuração Ativo")
    if st.button(get_text('change_language_button', language)):
        for key in list(st.session_state.keys()):
            if key not in ['language', 'debug_mode']: 
                del st.session_state[key]
        st.session_state.current_page = "LanguageSelection"
        st.rerun()

    summary = get_performance_summary(language)
    st.write("")
    kpi1, kpi2, kpi3 = st.columns(3)
    kpi1.metric(get_text('active_words_metric', language), summary['db_kpis']['ativas'])
    kpi2.metric(get_text('accuracy_metric', language), summary['kpis']['precisao'])
    kpi3.metric(get_text('sessions_metric', language), summary['kpis']['sessoes'])
    st.divider()

    st.markdown(f"<h2 class='section-header'>{get_text('practice_header', language)}</h2>", unsafe_allow_html=True)
    b1, b2, b3, b4 = st.columns(4)
    if b1.button(get_text('anki_quiz_button', language), use_container_width=True): st.session_state.current_page = "Quiz ANKI"; st.rerun()
    if b2.button(get_text('gpt_quiz_button', language), use_container_width=True): st.session_state.current_page = "Quiz GPT"; st.rerun()
    if b3.button(get_text('mixed_quiz_button', language), use_container_width=True): st.session_state.current_page = "Quiz Misto"; st.rerun()
    if b4.button(get_text('cloze_quiz_button', language), use_container_width=True): st.session_state.current_page = "Cloze Quiz"; st.rerun()

    st.markdown(f"<h2 class='section-header'>{get_text('reinforce_header', language)}</h2>", unsafe_allow_html=True)
    b5, b6 = st.columns(2)
    if b5.button(get_text('review_mode_button', language), use_container_width=True): st.session_state.current_page = "Modo de Revisão"; st.rerun()
    if b6.button(get_text('focus_mode_button', language), use_container_width=True): st.session_state.current_page = "Modo Foco"; st.rerun()

    st.markdown(f"<h2 class='section-header'>{get_text('analyze_header', language)}</h2>", unsafe_allow_html=True)
    b7, b8, b9 = st.columns(3)
    if b7.button(get_text('writing_mode_button', language), use_container_width=True): st.session_state.current_page = "Modo de Escrita"; st.rerun()
    if b8.button(get_text('sentence_writing_button', language), use_container_width=True):
        if 'word_sentence_index' in st.session_state:
            del st.session_state['word_sentence_index']
        st.session_state.current_page = "Sentence Writing"
        st.rerun()
    if b9.button(get_text('stats_button', language), use_container_width=True): st.session_state.current_page = "Estatísticas"; st.rerun()

def render_language_selection():
    st.markdown(f"<h1 class='main-title'>{get_text('app_title', 'en')}</h1>", unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    with col1:
        st.session_state.debug_mode = st.toggle(get_text('debug_mode_toggle', 'en'), value=st.session_state.get('debug_mode', False))
    with col2:
        if st.button(get_text('clear_cache_button', 'en'), use_container_width=True):
            st.cache_data.clear()
            st.success(get_text('cache_cleared_success', 'en'))
            st.rerun()
    st.divider()

    summary_en = get_performance_summary('en')
    summary_fr = get_performance_summary('fr')
    st.markdown(f"<h2 class='section-header'>{get_text('progress_overview_header', 'en')}</h2>", unsafe_allow_html=True)
    c1, c2 = st.columns(2)

    with c1:
        st.subheader("English 🇨🇦")
        if st.button(get_text('practice_english_button', 'en'), use_container_width=True):
            st.session_state.language = 'en'
            st.session_state.current_page = 'Homepage'
            st.rerun()
        
        st.markdown("##### " + get_text("mastery_pie_chart_title", "en"))
        pie_data_en = summary_en.get('pie_data', {})
        if sum(pie_data_en.values()) > 0:
            pie_df = pd.DataFrame(list(pie_data_en.items()), columns=['Status', 'Count'])
            pie_chart = alt.Chart(pie_df).mark_arc(innerRadius=50).encode(
                theta=alt.Theta(field="Count", type="quantitative"),
                color=alt.Color(field="Status", type="nominal"),
                tooltip=['Status', 'Count']
            ).configure_view(
                strokeWidth=0
            )
            st.altair_chart(pie_chart, use_container_width=True)
        else:
            st.info(get_text("no_progress_data", "en"))
        
        st.markdown("##### " + get_text("progress_distribution_title", "en"))
        dist_data_en = summary_en.get('distribution_data')
        if dist_data_en is not None and not dist_data_en.empty:
            dist_df = dist_data_en.reset_index()
            dist_df.columns = ['Progress Range', 'Number of Words']
            bar_chart = alt.Chart(dist_df).mark_bar().encode(
                x=alt.X('Progress Range', sort=None, title="Progress"),
                y=alt.Y('Number of Words', title="Words"),
                tooltip=['Progress Range', 'Number of Words']
            ).configure_view(
                strokeWidth=0
            )
            st.altair_chart(bar_chart, use_container_width=True)
        else:
            st.info(get_text("no_progress_data", "en"))

        st.markdown("<hr>", unsafe_allow_html=True)
        st.markdown("##### " + get_text("error_ranking_title", "en"))
        error_ranking_en = summary_en.get('error_ranking', [])
        if error_ranking_en:
            cols = st.columns(len(error_ranking_en[:3]))
            medals = ["🥇", "🥈", "🥉"]
            for i, (word, count, days) in enumerate(error_ranking_en[:3]):
                with cols[i]:
                    st.markdown(f"<div style='text-align: center; font-size: 2em;'>{medals[i]}</div>", unsafe_allow_html=True)
                    st.metric(label=f"{word}", value=f"{count} errors", delta=f"{days} days old", delta_color="off")
            
            if len(error_ranking_en) > 3:
                with st.expander(get_text("see_full_ranking_button", "en")):
                    for i, (word, count, days) in enumerate(error_ranking_en[3:], start=4):
                        st.write(f"**{i}. {word}**: {count} errors ({days} days old)")
        else:
            st.info(get_text("no_errors_to_rank", "en"))

        st.markdown("##### " + get_text("age_ranking_title", "en"))
        age_ranking_en = summary_en.get('age_ranking', [])
        if age_ranking_en:
            cols = st.columns(len(age_ranking_en[:3]))
            medals = ["🥇", "🥈", "🥉"]
            for i, (word, days) in enumerate(age_ranking_en[:3]):
                with cols[i]:
                    st.markdown(f"<div style='text-align: center; font-size: 2em;'>{medals[i]}</div>", unsafe_allow_html=True)
                    st.metric(label=word, value=f"{days} days")
            
            if len(age_ranking_en) > 3:
                with st.expander(get_text("see_full_ranking_button", "en")):
                    for i, (word, days) in enumerate(age_ranking_en[3:], start=4):
                        st.write(f"**{i}. {word}**: {days} days")
        else:
            st.info(get_text("no_words_to_rank_by_age", "en"))

    with c2:
        st.subheader("Français 🇫🇷")
        if st.button(get_text('practice_french_button', 'fr'), use_container_width=True):
            st.session_state.language = 'fr'
            st.session_state.current_page = 'Homepage'
            st.rerun()

        st.markdown("##### " + get_text("mastery_pie_chart_title", "fr"))
        pie_data_fr = summary_fr.get('pie_data', {})
        if sum(pie_data_fr.values()) > 0:
            pie_df = pd.DataFrame(list(pie_data_fr.items()), columns=['Statut', 'Décompte'])
            pie_chart = alt.Chart(pie_df).mark_arc(innerRadius=50).encode(
                theta=alt.Theta(field="Décompte", type="quantitative"),
                color=alt.Color(field="Statut", type="nominal"),
                tooltip=['Statut', 'Décompte']
            ).configure_view(
                strokeWidth=0
            )
            st.altair_chart(pie_chart, use_container_width=True)
        else:
            st.info(get_text("no_progress_data", "fr"))
        
        st.markdown("##### " + get_text("progress_distribution_title", "fr"))
        dist_data_fr = summary_fr.get('distribution_data')
        if dist_data_fr is not None and not dist_data_fr.empty:
            dist_df = dist_data_fr.reset_index()
            dist_df.columns = ['Plage de Progrès', 'Nombre de Mots']
            bar_chart = alt.Chart(dist_df).mark_bar().encode(
                x=alt.X('Plage de Progrès', sort=None, title="Progrès"),
                y=alt.Y('Nombre de Mots', title="Mots"),
                tooltip=['Plage de Progrès', 'Nombre de Mots']
            ).configure_view(
                strokeWidth=0
            )
            st.altair_chart(bar_chart, use_container_width=True)
        else:
            st.info(get_text("no_progress_data", "fr"))

        st.markdown("<hr>", unsafe_allow_html=True)
        st.markdown("##### " + get_text("error_ranking_title", "fr"))
        error_ranking_fr = summary_fr.get('error_ranking', [])
        if error_ranking_fr:
            cols = st.columns(len(error_ranking_fr[:3]))
            medals = ["🥇", "🥈", "🥉"]
            for i, (word, count, days) in enumerate(error_ranking_fr[:3]):
                with cols[i]:
                    st.markdown(f"<div style='text-align: center; font-size: 2em;'>{medals[i]}</div>", unsafe_allow_html=True)
                    st.metric(label=f"{word}", value=f"{count} erreurs", delta=f"{days} jours", delta_color="off")
            
            if len(error_ranking_fr) > 3:
                with st.expander(get_text("see_full_ranking_button", "fr")):
                    for i, (word, count, days) in enumerate(error_ranking_fr[3:], start=4):
                        st.write(f"**{i}. {word}**: {count} erreurs ({days} jours)")
        else:
            st.info(get_text("no_errors_to_rank", "fr"))

        st.markdown("##### " + get_text("age_ranking_title", "fr"))
        age_ranking_fr = summary_fr.get('age_ranking', [])
        if age_ranking_fr:
            cols = st.columns(len(age_ranking_fr[:3]))
            medals = ["🥇", "🥈", "🥉"]
            for i, (word, days) in enumerate(age_ranking_fr[:3]):
                with cols[i]:
                    st.markdown(f"<div style='text-align: center; font-size: 2em;'>{medals[i]}</div>", unsafe_allow_html=True)
                    st.metric(label=word, value=f"{days} jours")
            
            if len(age_ranking_fr) > 3:
                with st.expander(get_text("see_full_ranking_button", "fr")):
                    for i, (word, days) in enumerate(age_ranking_fr[3:], start=4):
                        st.write(f"**{i}. {word}**: {days} jours")
        else:
            st.info(get_text("no_words_to_rank_by_age", "en"))


def main():
    if "language" not in st.session_state: st.session_state.language = None
    if "current_page" not in st.session_state: st.session_state.current_page = "LanguageSelection"
    if "debug_mode" not in st.session_state: st.session_state.debug_mode = False
    
    page = st.session_state.current_page
    debug_mode = st.session_state.debug_mode
    language = st.session_state.language

    if language:
        inject_language_specific_css(language)

    if page == "LanguageSelection":
        render_language_selection()
    else:
        flashcards, gpt_exercicios = load_and_cache_data(language)
        
        if page == "Homepage": 
            render_homepage(language, debug_mode)
        elif page == "Quiz ANKI":
            from modules.quiz_ui import quiz_ui
            quiz_ui(flashcards, gpt_exercicios, language, debug_mode)
        elif page == "Quiz GPT":
            from modules.gpt_quiz_ui import gpt_ex_ui
            gpt_ex_ui(gpt_exercicios, language, debug_mode)
        elif page == "Quiz Misto":
            from modules.mixed_quiz_ui import mixed_quiz_ui
            mixed_quiz_ui(flashcards, gpt_exercicios, language, debug_mode)
        elif page == "Cloze Quiz":
            from modules.cloze_quiz_ui import cloze_quiz_ui
            cloze_quiz_ui(gpt_exercicios, language, debug_mode)
        elif page == "Modo de Escrita":
            from modules.writing_ui import writing_ui
            writing_ui(language, debug_mode)
        elif page == "Estatísticas":
            from modules.stats_ui import estatisticas_ui
            estatisticas_ui(language)
        elif page == "Modo de Revisão":
            from modules.review_quiz_ui import review_quiz_ui
            review_quiz_ui(flashcards, gpt_exercicios, language, debug_mode)
        elif page == "Modo Foco":
            from modules.focus_quiz_ui import focus_quiz_ui
            focus_quiz_ui(flashcards, gpt_exercicios, language, debug_mode)
        elif page == "Sentence Writing":
            from modules.sentence_writing_ui import sentence_writing_ui
            sentence_writing_ui(language, debug_mode)

if __name__ == "__main__":
    main()
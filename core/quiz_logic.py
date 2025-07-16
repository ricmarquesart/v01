import random
from collections import defaultdict
from core.data_manager import TIPOS_EXERCICIO_ANKI, get_available_exercise_types_for_word
import re

def selecionar_questoes_priorizadas(palavras_ativas, flashcards_map, gpt_exercicios_map, N, tipo_filtro="Random"):
    """
    Cria uma lista de questões para o quiz, garantindo a máxima diversidade de palavras.
    """
    if palavras_ativas.empty:
        return []

    # --- NOVA LÓGICA DE SELEÇÃO ---

    # 1. Seleciona N palavras únicas para garantir a diversidade.
    palavras_disponiveis = palavras_ativas.sample(frac=1) # Embaralha para não pegar sempre as mesmas
    palavras_selecionadas = palavras_disponiveis.head(N)

    playlist = []
    for _, palavra_info in palavras_selecionadas.iterrows():
        palavra = palavra_info['palavra']
        progresso = palavra_info.get('progresso', {})
        
        # 2. Para cada palavra, obtém todos os seus exercícios únicos.
        exercicios_da_palavra = get_available_exercise_types_for_word(palavra, flashcards_map, gpt_exercicios_map)

        # 3. Filtra os exercícios por tipo, se um filtro for aplicado.
        exercicios_filtrados = {
            identificador: tipo for identificador, tipo in exercicios_da_palavra.items()
            if tipo_filtro == "Random" or tipo == tipo_filtro
        }

        if not exercicios_filtrados:
            continue

        # 4. Prioriza exercícios não feitos ou errados.
        alta_prioridade = [
            {'palavra': palavra, 'tipo_exercicio': tipo, 'identificador': id_ex}
            for id_ex, tipo in exercicios_filtrados.items()
            if progresso.get(id_ex) != 'acerto'
        ]
        
        baixa_prioridade = [
            {'palavra': palavra, 'tipo_exercicio': tipo, 'identificador': id_ex}
            for id_ex, tipo in exercicios_filtrados.items()
            if progresso.get(id_ex) == 'acerto'
        ]

        # 5. Escolhe um exercício para a palavra (dando preferência aos de alta prioridade).
        if alta_prioridade:
            playlist.append(random.choice(alta_prioridade))
        elif baixa_prioridade:
            playlist.append(random.choice(baixa_prioridade))
            
    # Embaralha a playlist final para que as palavras não apareçam sempre na mesma ordem
    random.shuffle(playlist)
    return playlist

def gerar_questao_dinamica(item_playlist, flashcards, gpt_exercicios, db_completo):
    """
    Gera os detalhes de uma questão com alternativas erradas totalmente aleatórias.
    """
    palavra = item_playlist['palavra']
    tipo_exercicio = item_playlist['tipo_exercicio']
    
    flashcards_map = {card['front']: card for card in flashcards}
    gpt_exercicios_map = defaultdict(list)
    for ex in gpt_exercicios:
        if isinstance(ex.get('principal'), str):
            gpt_exercicios_map[ex['principal']].append(ex)

    fonte = "ANKI" if tipo_exercicio in TIPOS_EXERCICIO_ANKI else "GPT"
    
    if fonte == 'ANKI':
        cartao = flashcards_map.get(palavra)
        if cartao:
            generator_func = TIPOS_EXERCICIO_ANKI.get(tipo_exercicio)
            if generator_func:
                return generator_func(cartao, flashcards)
    
    elif fonte == 'GPT':
        identificador = item_playlist.get('identificador')
        exercicios_disponiveis = [
            ex for ex in gpt_exercicios_map.get(palavra, []) 
            if ex.get('tipo') == tipo_exercicio and ex.get('frase') == identificador
        ]

        if exercicios_disponiveis:
            exercicio = exercicios_disponiveis[0]
            pergunta = re.sub(rf'{re.escape(exercicio["principal"])}', f'<span class="keyword-highlight">{exercicio["principal"]}</span>', exercicio["frase"], flags=re.IGNORECASE)
            
            correta = exercicio['correta']
            opcoes = exercicio['opcoes']
            keyword = exercicio['principal']
            
            tipos_para_filtrar_keyword = ["2-Word-Meaning", "3-Paraphrase", "4-Minimal-Pair"]
            if tipo_exercicio in tipos_para_filtrar_keyword:
                opcoes_filtradas = [opt for opt in opcoes if opt.lower() != keyword.lower()]
            else:
                opcoes_filtradas = opcoes

            opcoes = list(set(opcoes_filtradas))

            if len(opcoes) < 4:
                necessarios = 4 - len(opcoes)
                palavras_existentes = {opt.lower() for opt in opcoes}
                palavras_existentes.add(keyword.lower())
                palavras_existentes.add(correta.lower())
                pool_distratores = [p for p in db_completo['palavra'].tolist() if p.lower() not in palavras_existentes]
                if len(pool_distratores) >= necessarios:
                    novos_distratores = random.sample(pool_distratores, k=necessarios)
                    opcoes.extend(novos_distratores)

            random.shuffle(opcoes)
            
            if correta not in opcoes:
                return None, None, [], -1, None, None
            
            cefr_level = exercicio.get('cefr_level')
            return exercicio['tipo'], pergunta, opcoes, opcoes.index(correta), cefr_level, identificador
            
    return None, None, [], -1, None, None

def selecionar_questoes_gpt(palavras_ativas, gpt_exercicios_map, tipo_filtro, n_palavras, repetir):
    """Cria uma lista de questões para o Quiz GPT com aleatoriedade melhorada."""
    exercicios_possiveis = []
    palavras_ativas_set = set(palavras_ativas['palavra'].values)
    
    for palavra, exercicios in gpt_exercicios_map.items():
        if palavra in palavras_ativas_set:
            for ex in exercicios:
                if tipo_filtro == "Random" or ex.get('tipo') == tipo_filtro:
                    progresso_palavra = palavras_ativas[palavras_ativas['palavra'] == palavra].iloc[0].get('progresso', {})
                    status = progresso_palavra.get(ex.get('frase'), 'nao_testado')
                    prioridade = 0 if status != 'acerto' else 1
                    exercicios_possiveis.append((prioridade, random.random(), ex))

    exercicios_possiveis.sort()

    playlist = []
    if not repetir:
        # Se não for para repetir, a lógica precisa garantir diversidade de palavras
        palavras_unicas = list(set(ex['principal'] for _, _, ex in exercicios_possiveis))
        random.shuffle(palavras_unicas)
        palavras_selecionadas = palavras_unicas[:n_palavras]
        
        for palavra in palavras_selecionadas:
            questoes_da_palavra = [ex for _, _, ex in exercicios_possiveis if ex['principal'] == palavra]
            if questoes_da_palavra:
                playlist.append(random.choice(questoes_da_palavra))
    else:
        # Se puder repetir, apenas pega o número desejado de exercícios de alta prioridade
        playlist = [ex for _, _, ex in exercicios_possiveis[:n_palavras]]

    random.shuffle(playlist)
    return playlist
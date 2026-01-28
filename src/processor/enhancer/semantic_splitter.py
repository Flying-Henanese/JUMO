import re
import nltk
from nltk.tokenize import sent_tokenize
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics import silhouette_score
from processor.nlp_inference.factory import InferenceFactory

# Ensure punkt_tab is available
try:
    nltk.data.find('tokenizers/punkt_tab')
except LookupError:
    nltk.download('punkt_tab')

def split_sentences_chinese(text):
    """
    Split sentences by Chinese punctuation while keeping the punctuation.
    """
    # 1. (?<=[。！？])(?![”’"]) : Match punctuation not followed by a quote
    # 2. (?<=[。！？][”’"])    : Match punctuation followed by a quote
    pattern = r'(?<=[。！？])(?![”’"])|(?<=[。！？][”’"])'
    sentences = re.split(pattern, text)
    return [s.strip() for s in sentences if s.strip()]

def split_mixed_sentences(text: str) -> list[str]:
    """
    Handle both Chinese and English sentence splitting.
    English uses NLTK; Chinese uses regex.
    """
    chunks = re.split(r'(\n+)', text)
    sentences = []

    for ch in chunks:
        if not ch.strip():
            continue
        # English paragraph check: contains letters and ends with sentence terminators
        if re.search(r'[A-Za-z]', ch):
            parts = sent_tokenize(ch)
            sentences.extend([p.strip() for p in parts if p.strip()])
        # Chinese paragraph
        else:
            sents = split_sentences_chinese(ch)
            if sents:
                sentences.extend([s.strip() for s in sents if s.strip()])
            else:
                parts = re.split(r'(?<=[。！？])', ch)
                sentences.extend([p.strip() for p in parts if p.strip()])
    return sentences

def find_best_num_clusters(embeddings, min_clusters=2, max_clusters=10):
    """
    Select best number of clusters using silhouette score.
    """
    best_score = -1
    best_k = min_clusters

    for k in range(min_clusters, min(max_clusters, len(embeddings)) + 1):
        labels = AgglomerativeClustering(n_clusters=k, metric='cosine', linkage='average').fit_predict(embeddings)
        if len(set(labels)) == 1:
            continue
        score = silhouette_score(embeddings, labels, metric='cosine')
        if score > best_score:
            best_score = score
            best_k = k

    return best_k

def semantic_chunking_with_auto_clusters(text, max_chunk_size=500, model_id="BAAI/bge-small-zh-v1.5"):
    """
    Semantic chunking with automatic cluster number selection.
    """
    # Step 1: Split sentences
    sentences = split_mixed_sentences(text)
    if len(sentences) < 2:
        return [text.strip()]

    # Step 2: Vectorization
    client = InferenceFactory.get_embedding_client()
    embeddings = client.encode(sentences)

    # Step 3: Determine number of clusters
    # Simple heuristic: number of sentences // max_chunk_size + 1
    best_k = max(len(sentences)//max_chunk_size, 1) + 1
    
    # Step 4: Clustering
    labels = AgglomerativeClustering(n_clusters=best_k, metric='cosine', linkage='average').fit_predict(embeddings)

    # Step 5: Group sentences by cluster and limit chunk size
    chunks = []
    current_chunk = ""
    current_label = labels[0]

    for sentence, label in zip(sentences, labels):
        if label != current_label or len(current_chunk) + len(sentence) > max_chunk_size:
            if current_chunk.strip():
                chunks.append(current_chunk.strip())
            current_chunk = sentence
            current_label = label
        else:
            current_chunk += sentence

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks
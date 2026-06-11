from sentence_transformers import SentenceTransformer
from sentence_transformers import InputExample
from sentence_transformers import losses

from torch.utils.data import DataLoader
#from sentence_transformers.training_args import BatchSamplers

from torch.utils.data import DataLoader, Dataset
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
import logging

logging.basicConfig(
    level=logging.INFO,format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ----------------------------
# Training Data
# ----------------------------
try:
    logger.info("Preparing training data...")
    train_examples = [

        InputExample(
            texts=[
                "What is artificial intelligence?",
                "AI is the simulation of human intelligence"
            ]
        ),

        InputExample(
            texts=[
                "How to learn Python?",
                "Python programming tutorial for beginners"
            ]
        ),

        InputExample(
            texts=[
                "What is deep learning?",
                "Deep learning uses neural networks"
            ]
        ),

        InputExample(
            texts=[
                "What is machine learning?",
                "Machine learning enables systems to learn from data"
            ]
        ),

        InputExample(
            texts=[
                "How to cook rice?",
                "Steps to prepare cooked rice"
            ]
        ),
    ]

    # ----------------------------
    # Load Base Transformer
    # ----------------------------

    model = SentenceTransformer(
        "all-MiniLM-L6-v2"
    )

    # ----------------------------
    # Data Loader
    # ----------------------------

    from torch.utils.data import Dataset

    class ExampleDataset(Dataset):
        def __init__(self, examples):
            self.examples = examples

        def __len__(self):
            return len(self.examples)

        def __getitem__(self, idx):
            return self.examples[idx]

    train_dataset = ExampleDataset(train_examples)

    train_dataloader = DataLoader(
        train_dataset,
        shuffle=True,
        batch_size=2,
        collate_fn=lambda x: x
    )

    # ----------------------------
    # Loss Function
    # ----------------------------

    train_loss = losses.MultipleNegativesRankingLoss(
        model
    )

    # ----------------------------
    # Train Model
    # ----------------------------

    print("Training started...")

    model.fit(
        train_objectives=[
            (train_dataloader, train_loss)
        ],
        epochs=3,
        warmup_steps=10,
        show_progress_bar=True
    )

    print("Training finished")

    # ----------------------------
    # Save Model
    # ----------------------------

    model_path = "smart_ai_embedding_model"

    model.save(model_path)

    print(f"Model saved to: {model_path}")

    # ----------------------------
    # Load Saved Model
    # ----------------------------

    loaded_model = SentenceTransformer(
        model_path
    )

    # ----------------------------
    # Test Embeddings
    # ----------------------------

    sentences = [
        "Artificial intelligence systems",
        "Machine learning models",
        "Cooking food at home"
    ]

    embeddings = loaded_model.encode(sentences)

    print("\nEmbedding Shape:")
    print(embeddings.shape)

    # ----------------------------
    # Similarity Test
    # ----------------------------

    similarity = cosine_similarity(
        np.array([embeddings[0]]),
        np.array([embeddings[1]])
    )

    print("\nSimilarity between AI and ML:")
    print(similarity[0][0])

    similarity2 = cosine_similarity(
        np.array([embeddings[0]]),
        np.array([embeddings[2]])
    )

    print("\nSimilarity between AI and Cooking:")
    print(similarity2[0][0])
except Exception as e:
    logger.error(f"An error occurred: {e}")
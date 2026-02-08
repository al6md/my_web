import torch
import torch.nn as nn
import torch.nn.functional as F

class UserTower(nn.Module):
    def __init__(self, user_embedding_dim=128, history_input_dim=384, hidden_dim=256, output_dim=384):
        super(UserTower, self).__init__()
        
        # 1. User Identity Embedding (Personal Bias) -- Expanded to 50k users
        self.user_embedding = nn.Embedding(50000, user_embedding_dim)
        
        # 2. Sequential History Encoder (Transformer)
        # We process the sequence of book embeddings viewed/read by the user.
        encoder_layer = nn.TransformerEncoderLayer(d_model=history_input_dim, nhead=8, batch_first=True)
        self.history_transformer = nn.TransformerEncoder(encoder_layer, num_layers=2)
        
        # Aggregating the sequence - Linear projection
        self.history_pooler = nn.Linear(history_input_dim, hidden_dim)

        # 3. Explicit Interests (Genres/Topics)
        # Assuming input is a mean vector of all interest embeddings
        self.interest_projector = nn.Linear(history_input_dim, hidden_dim)
        
        # 4. Fusion Layer
        # Concatenate: UserID(128) + History(256) + Interest(256)
        fusion_dim = user_embedding_dim + hidden_dim + hidden_dim
        
        self.fc1 = nn.Linear(fusion_dim, hidden_dim)
        self.bn1 = nn.BatchNorm1d(hidden_dim)
        self.dropout = nn.Dropout(0.3)
        self.fc2 = nn.Linear(hidden_dim, output_dim) # Final Embedding Space
        
    def forward(self, user_ids, history_vectors, interest_vectors):
        """
        user_ids: (Batch,)
        history_vectors: (Batch, Seq_Len, 384) - Embeddings of books read
        interest_vectors: (Batch, 384) - Mean embedding of liked genres
        """
        # A. User ID Features
        u_emb = self.user_embedding(user_ids) # (B, 128)
        
        # B. History Features (Transformer Attention)
        # Pass through Transformer
        hist_trans = self.history_transformer(history_vectors) # (B, Seq, 384)
        # Mean pooling over sequence for simple representation, or take last text
        hist_pooled = hist_trans.mean(dim=1) # (B, 384)
        hist_rep = F.relu(self.history_pooler(hist_pooled)) # (B, 256)
        
        # C. Interest Features
        int_rep = F.relu(self.interest_projector(interest_vectors)) # (B, 256)
        
        # D. Fusion
        combined = torch.cat([u_emb, hist_rep, int_rep], dim=1)
        
        x = self.fc1(combined)
        x = self.bn1(x)
        x = F.gelu(x)
        x = self.dropout(x)
        x = self.fc2(x)
        
        # Normalize for Cosine Similarity
        return F.normalize(x, p=2, dim=1)

class BookTower(nn.Module):
    def __init__(self, input_dim=384, hidden_dim=256, output_dim=384):
        super(BookTower, self).__init__()
        
        # Deep Cross Network or simple MLP for Item Features
        # Input: The SentenceTransformer embedding of Title + Description
        
        self.fc1 = nn.Linear(input_dim, hidden_dim)
        self.bn1 = nn.BatchNorm1d(hidden_dim)
        self.fc2 = nn.Linear(hidden_dim, hidden_dim)
        self.dropout = nn.Dropout(0.2)
        self.fc3 = nn.Linear(hidden_dim, output_dim)
        
    def forward(self, book_vectors):
        """
        book_vectors: (Batch, 768)
        """
        x = self.fc1(book_vectors)
        x = self.bn1(x)
        x = F.gelu(x) # GELU is SOTA for Transformer-like archs
        x = self.dropout(x)
        x = F.gelu(self.fc2(x))
        x = self.fc3(x)
        
        return F.normalize(x, p=2, dim=1)

class SuperIntelligentTwoTower(nn.Module):
    def __init__(self):
        super(SuperIntelligentTwoTower, self).__init__()
        self.user_tower = UserTower()
        self.book_tower = BookTower()
        
    def forward(self, user_data, book_data):
        """
        user_data: tuple(user_ids, history_seq, interest_vec)
        book_data: tensor(book_vec)
        """
        u_vec = self.user_tower(*user_data)
        b_vec = self.book_tower(book_data)
        return u_vec, b_vec
        
    def predict_score(self, user_data, book_data):
        u, b = self.forward(user_data, book_data)
        # Cosine Similarity (-1 to 1)
        return (u * b).sum(dim=1)

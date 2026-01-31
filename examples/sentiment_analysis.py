import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, accuracy_score
import joblib
import re
import nltk
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer

# Download required NLTK data (run once)
nltk.download('stopwords')
nltk.download('wordnet')

class SentimentAnalysisWorkflow:
    def __init__(self):
        self.vectorizer = TfidfVectorizer(max_features=5000)
        self.model = LogisticRegression(random_state=42)
        self.lemmatizer = WordNetLemmatizer()
        self.stop_words = set(stopwords.words('english'))
    
    def preprocess_text(self, text):
        """Step 1: Data Preprocessing"""
        # Convert to lowercase
        text = text.lower()
        # Remove special characters and digits
        text = re.sub(r'[^a-zA-Z\s]', '', text)
        # Remove extra whitespace
        text = ' '.join(text.split())
        # Tokenize and remove stopwords
        words = text.split()
        words = [self.lemmatizer.lemmatize(word) for word in words if word not in self.stop_words]
        return ' '.join(words)
    
    def prepare_data(self):
        """Step 2: Data Preparation"""
        # Create sample dataset (in real scenario, you'd load from CSV/database)
        data = {
            'review': [
                "I love this product! It's amazing and works perfectly.",
                "This is the worst purchase I've ever made.",
                "Great quality and fast delivery. Highly recommended!",
                "Poor quality product. Broke after 2 days of use.",
                "Excellent service and good customer support.",
                "Terrible experience. Will never buy again.",
                "The product is okay, nothing special.",
                "Outstanding performance and great value for money.",
                "Disappointed with the quality. Not as described.",
                "Fast shipping and product works as expected."
            ],
            'sentiment': [1, 0, 1, 0, 1, 0, 1, 1, 0, 1]  # 1=Positive, 0=Negative
        }
        
        # Add more samples to make it more realistic
        positive_reviews = [
            "Absolutely fantastic! Exceeded my expectations.",
            "Very happy with this purchase. Works great!",
            "Good value and excellent quality.",
            "Perfect for my needs. Very satisfied.",
            "Quick delivery and good packaging."
        ]
        
        negative_reviews = [
            "Waste of money. Don't buy this.",
            "Poor craftsmanship and cheap materials.",
            "Arrived damaged and customer service was unhelpful.",
            "Not worth the price. Very disappointed.",
            "Stopped working after a week. Poor quality."
        ]
        
        for review in positive_reviews:
            data['review'].append(review)
            data['sentiment'].append(1)
            
        for review in negative_reviews:
            data['review'].append(review)
            data['sentiment'].append(0)
        
        return pd.DataFrame(data)
    
    def train_model(self, df):
        """Step 3: Model Training"""
        print("🔧 Step 1: Preprocessing text data...")
        df['cleaned_review'] = df['review'].apply(self.preprocess_text)
        
        print("🔧 Step 2: Feature extraction...")
        X = self.vectorizer.fit_transform(df['cleaned_review'])
        y = df['sentiment']
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )
        
        print("🔧 Step 3: Training model...")
        self.model.fit(X_train, y_train)
        
        print("🔧 Step 4: Model evaluation...")
        y_pred = self.model.predict(X_test)
        accuracy = accuracy_score(y_test, y_pred)
        
        print(f"✅ Model trained successfully!")
        print(f"📊 Accuracy: {accuracy:.2f}")
        print("\n📈 Classification Report:")
        print(classification_report(y_test, y_pred))
        
        return X_test, y_test
    
    def predict_sentiment(self, text):
        """Step 4: Inference/Prediction"""
        # Preprocess the input text
        cleaned_text = self.preprocess_text(text)
        # Transform using the fitted vectorizer
        text_vector = self.vectorizer.transform([cleaned_text])
        # Make prediction
        prediction = self.model.predict(text_vector)[0]
        probability = self.model.predict_proba(text_vector)[0]
        
        sentiment = "Positive" if prediction == 1 else "Negative"
        confidence = probability[prediction]
        
        return {
            'text': text,
            'sentiment': sentiment,
            'confidence': confidence,
            'probabilities': {
                'negative': probability[0],
                'positive': probability[1]
            }
        }
    
    def save_model(self, filepath):
        """Step 5: Save the trained model"""
        model_data = {
            'vectorizer': self.vectorizer,
            'model': self.model
        }
        joblib.dump(model_data, filepath)
        print(f"💾 Model saved to {filepath}")
    
    def load_model(self, filepath):
        """Load a trained model"""
        model_data = joblib.load(filepath)
        self.vectorizer = model_data['vectorizer']
        self.model = model_data['model']
        print(f"📂 Model loaded from {filepath}")

def main():
    """Complete AI Workflow Execution"""
    print("🚀 Starting AI Workflow: Sentiment Analysis System\n")
    
    # Initialize the workflow
    workflow = SentimentAnalysisWorkflow()
    
    # Step 1: Prepare data
    print("📊 Step 1: Preparing data...")
    df = workflow.prepare_data()
    print(f"   Loaded {len(df)} reviews")
    print(f"   Positive reviews: {sum(df['sentiment'] == 1)}")
    print(f"   Negative reviews: {sum(df['sentiment'] == 0)}\n")
    
    # Step 2: Train model
    print("🤖 Step 2: Training the model...")
    X_test, y_test = workflow.train_model(df)
    
    # Step 3: Save model
    print("\n💾 Step 3: Saving the model...")
    workflow.save_model('sentiment_model.pkl')
    
    # Step 4: Test predictions
    print("\n🔮 Step 4: Testing predictions...")
    test_reviews = [
        "This product is absolutely wonderful!",
        "I hate this thing, it's terrible.",
        "The quality is good but delivery was slow.",
        "Excellent product with great features!",
        "Poor quality and bad customer service."
    ]
    
    print("\n📝 Prediction Results:")
    print("-" * 50)
    for review in test_reviews:
        result = workflow.predict_sentiment(review)
        print(f"Review: {result['text']}")
        print(f"Sentiment: {result['sentiment']} (Confidence: {result['confidence']:.2f})")
        print(f"Probabilities - Negative: {result['probabilities']['negative']:.3f}, "
              f"Positive: {result['probabilities']['positive']:.3f}")
        print("-" * 50)

# Advanced version with batch processing
def batch_sentiment_analysis():
    """Example of batch processing workflow"""
    print("\n" + "="*60)
    print("🔄 BATCH PROCESSING WORKFLOW")
    print("="*60)
    
    workflow = SentimentAnalysisWorkflow()
    
    # Simulate loading new batch of data
    batch_reviews = [
        "Love this product! Will buy again.",
        "Terrible quality, very disappointed.",
        "Good value for money.",
        "Not as described, poor packaging.",
        "Excellent service and fast shipping!",
        "Broken upon arrival. Very unhappy.",
        "Great features and easy to use.",
        "Waste of money, doesn't work properly."
    ]
    
    print("Processing batch of reviews...")
    results = []
    for review in batch_reviews:
        result = workflow.predict_sentiment(review)
        results.append(result)
    
    # Analyze batch results
    positive_count = sum(1 for r in results if r['sentiment'] == 'Positive')
    negative_count = sum(1 for r in results if r['sentiment'] == 'Negative')
    
    print(f"\n📈 Batch Analysis Summary:")
    print(f"   Total reviews: {len(results)}")
    print(f"   Positive: {positive_count} ({positive_count/len(results)*100:.1f}%)")
    print(f"   Negative: {negative_count} ({negative_count/len(results)*100:.1f}%)")
    
    # Show low confidence predictions
    low_confidence = [r for r in results if r['confidence'] < 0.7]
    if low_confidence:
        print(f"\n⚠️  Low confidence predictions (needs human review):")
        for r in low_confidence:
            print(f"   - '{r['text']}' (Confidence: {r['confidence']:.2f})")

if __name__ == "__main__":
    # Run the main workflow
    main()
    
    # Run batch processing example
    batch_sentiment_analysis()
    
    print("\n✅ AI Workflow Completed Successfully!")



import spacy
from spacy.tokens import DocBin
from spacy.training import Example
import json
from pathlib import Path
from typing import List, Dict, Any

def load_training_data() -> List[Dict[str, Any]]:
    """Load training data from JSON file"""
    data_path = Path("data/training_data.json")
    if not data_path.exists():
        raise FileNotFoundError(f"Training data not found at {data_path}")
        
    with open(data_path, "r", encoding="utf-8") as f:
        return json.load(f)

def create_custom_components(nlp):
    """Create custom pipeline components"""
    # Configure text categorizer
    config = {
        "@architectures": "spacy.TextCatEnsemble.v2",
        "scorer": {"@scorers": "spacy.textcat_multilabel_scorer.v2"},
        "threshold": 0.3
    }
    
    # Remove existing textcat if present
    if "textcat" in nlp.pipe_names:
        nlp.remove_pipe("textcat")
    
    # Add new textcat component
    textcat = nlp.add_pipe("textcat_multilabel", last=True)
    
    # Add labels
    textcat.add_label("acceptance")
    textcat.add_label("decline")
    textcat.add_label("reschedule")
    textcat.add_label("info_request")
    textcat.add_label("delegation")
    
    return nlp

def create_training_examples(nlp, training_data):
    """Convert training data to spaCy's Example format with proper label formatting"""
    examples = []
    for item in training_data:
        doc = nlp.make_doc(item["text"])
        
        # Convert probability-like values to binary (0 or 1)
        cats = {}
        for label, value in item["cats"].items():
            cats[label] = 1 if value >= 0.5 else 0
        
        # Create annotations dict with cats and entities
        annotations = {
            "cats": cats,
            "entities": item.get("entities", [])
        }
        
        # Add additional info as custom attributes if present
        if "additional_info" in item:
            doc.user_data["additional_info"] = item["additional_info"]
        
        examples.append(Example.from_dict(doc, annotations))
    
    return examples

def train_model():
    # Load base model
    nlp = spacy.load("en_core_web_sm")
    
    # Add custom components
    nlp = create_custom_components(nlp)
    
    # Load and prepare training data
    training_data = load_training_data()
    train_examples = create_training_examples(nlp, training_data)
    
    # Training settings
    n_iter = 20
    batch_size = 4
    
    # Train the model
    other_pipes = [pipe for pipe in nlp.pipe_names if pipe != "textcat_multilabel"]
    with nlp.disable_pipes(*other_pipes):
        optimizer = nlp.begin_training()
        
        # Training loop
        for i in range(n_iter):
            losses = {}
            batches = [train_examples[i:i + batch_size] 
                      for i in range(0, len(train_examples), batch_size)]
            
            for batch in batches:
                nlp.update(batch, sgd=optimizer, losses=losses)
            
            print(f"Iteration {i+1}, Losses:", losses)
    
    # Save custom attributes configuration
    config = {
        "additional_info_keys": [
            "uncertainty",
            "alternative_times_suggested",
            "delegate_name",
            "delegate_email",
            "original_time",
            "proposed_times"
        ],
        "custom_patterns": {
            "uncertainty": [
                "high chance",
                "depending on",
                "might be able",
                "not sure",
                "possibly",
                "tentative"
            ],
            "delegation": [
                "associate.*step in",
                "delegate to",
                "will handle",
                "take over"
            ]
        }
    }
    
    # Save model and configuration
    output_dir = Path("./custom_model")
    if not output_dir.exists():
        output_dir.mkdir(parents=True)
    
    # Save the model
    nlp.to_disk(output_dir)
    
    # Save the configuration
    with open(output_dir / "config.json", "w") as f:
        json.dump(config, f, indent=2)
    
    print(f"Model and configuration saved to {output_dir}")

if __name__ == "__main__":
    train_model() 
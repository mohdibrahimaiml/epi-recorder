import matplotlib.pyplot as plt
import numpy as np

def plot_performance_metrics(metrics):
    """Plot training metrics over epochs."""
    epochs = range(len(metrics['loss']))
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4))
    
    ax1.plot(epochs, metrics['loss'], 'b-', label='Training Loss')
    ax1.set_xlabel('Epochs')
    ax1.set_ylabel('Loss')
    ax1.legend()
    ax1.grid(True)
    
    ax2.plot(epochs, metrics['accuracy'], 'g-', label='Accuracy')
    ax2.set_xlabel('Epochs')
    ax2.set_ylabel('Accuracy')
    ax2.legend()
    ax2.grid(True)
    
    plt.tight_layout()
    plt.show()



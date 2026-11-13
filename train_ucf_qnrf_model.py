import os
import glob
import numpy as np
import scipy.io as io
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
import cv2

# ============================================================================
# UCF-QNRF DATASET LOADER & DENSITY MAP GENERATOR
# ============================================================================

class UCFQNRFDataset(Dataset):
    """
    Dataset loader for UCF-QNRF Crowd Dataset
    Loads images and .mat annotation files (head point coordinates)
    """
    def __init__(self, root_dir, mode='Train', transform=None, max_samples=100):
        self.root_dir = os.path.join(root_dir, mode)
        self.transform = transform
        self.img_paths = sorted(glob.glob(os.path.join(self.root_dir, "img_*.jpg")))[:max_samples]
        
    def __len__(self):
        return len(self.img_paths)
    
    def __getitem__(self, idx):
        img_path = self.img_paths[idx]
        mat_path = img_path.replace(".jpg", "_ann.mat")
        
        # Load image
        img = cv2.imread(img_path)
        if img is None:
            img = np.zeros((256, 256, 3), dtype=np.uint8)
        else:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        
        # Load head annotations
        try:
            mat = io.loadmat(mat_path)
            ann_points = mat['annPoints'] # (N, 2) array of x, y coords
            crowd_count = len(ann_points)
        except Exception as e:
            ann_points = np.zeros((0, 2))
            crowd_count = 0
            
        # Resize image for fast model processing (256x256)
        target_size = (256, 256)
        img_resized = cv2.resize(img, target_size)
        
        # Calculate crowd density score D_Score (0 - 100)
        density_score = min(100.0, (np.log1p(crowd_count) / np.log1p(2000.0)) * 100.0)
        
        # Convert to tensor
        img_tensor = torch.from_numpy(img_resized).permute(2, 0, 1).float() / 255.0
        
        return img_tensor, torch.tensor([density_score], dtype=torch.float32), crowd_count, img_path


class CrowdDensityRegressor(nn.Module):
    """
    CNN Architecture for Crowd Density Score Prediction (D_Score)
    """
    def __init__(self):
        super(CrowdDensityRegressor, self).__init__()
        self.features = nn.Sequential(
            nn.Conv2d(3, 32, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2, 2), # 128x128
            nn.Conv2d(32, 64, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2, 2), # 64x64
            nn.Conv2d(64, 128, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.AdaptiveAvgPool2d((8, 8))
        )
        self.fc = nn.Sequential(
            nn.Linear(128 * 8 * 8, 128),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(128, 1),
            nn.Sigmoid() # Scale 0 to 1 -> multiply by 100
        )
        
    def forward(self, x):
        x = self.features(x)
        x = x.view(x.size(0), -1)
        out = self.fc(x) * 100.0
        return out


def train_ucf_qnrf_model(dataset_path, epochs=3, max_samples=60):
    """
    Train crowd density regressor on UCF-QNRF dataset
    """
    print(f"\n{'='*80}")
    print("TRAINING CROWD DENSITY MODEL ON UCF-QNRF DATASET")
    print(f"{'='*80}")
    
    train_dataset = UCFQNRFDataset(dataset_path, mode='Train', max_samples=max_samples)
    train_loader = DataLoader(train_dataset, batch_size=8, shuffle=True)
    
    model = CrowdDensityRegressor()
    criterion = nn.MSELoss()
    optimizer = optim.Adam(model.parameters(), lr=1e-3)
    
    model.train()
    for epoch in range(epochs):
        running_loss = 0.0
        for i, (imgs, targets, counts, _) in enumerate(train_loader):
            optimizer.zero_grad()
            outputs = model(imgs)
            loss = criterion(outputs, targets)
            loss.backward()
            optimizer.step()
            running_loss += loss.item()
            
        print(f"Epoch [{epoch+1}/{epochs}] Loss: {running_loss / max(1, len(train_loader)):.4f}")
        
    print("[OK] Model training on UCF-QNRF completed successfully!")
    model_save_path = os.path.join(dataset_path, "..", "ucf_qnrf_density_model.pth")
    torch.save(model.state_dict(), model_save_path)
    print(f"[OK] Model saved to: {model_save_path}")
    return model

if __name__ == "__main__":
    dataset_dir = r"c:\Users\divig\Desktop\patent-crowd\Patent\UCF-QNRF_ECCV18"
    trained_model = train_ucf_qnrf_model(dataset_dir, epochs=3, max_samples=60)

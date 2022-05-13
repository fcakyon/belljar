import matplotlib.pyplot as plt 
import numpy as np
import torch
from torchvision import transforms
from torchsummary import summary
from torch.utils.data import DataLoader, Dataset, random_split
from torch.utils import tensorboard
from sklearn.model_selection import train_test_split
from torch import embedding, nn
import cv2
import os, pickle
from scipy import spatial
from scipy import stats
class Encoder(nn.Module):
    def __init__(self):
        super().__init__()
        
        # Initial cnn w/ batch norm
        self.stageOneCNN = nn.Sequential(
            nn.Conv2d(1,32, (3,3), 2, 1),
            nn.BatchNorm2d(32),
            nn.LeakyReLU(),
            nn.Conv2d(32,32,(3,3)),
            nn.LeakyReLU(),
        )

        self.stageTwoCNN = nn.Sequential(
            nn.Conv2d(32, 64, (3,3), 2, 1),
            nn.BatchNorm2d(64),
            nn.LeakyReLU(),
            nn.Conv2d(64, 64, (3,3)),
            nn.LeakyReLU(),
        )

        self.stageThreeCNN = nn.Sequential(
            nn.Conv2d(64, 128, (3,3), 2, 1),
            nn.BatchNorm2d(128),
            nn.LeakyReLU(),
            nn.Conv2d(128, 128, (3,3)),
            nn.LeakyReLU(),
        )

        self.stageFourCNN = nn.Sequential(
            nn.Conv2d(128, 256, (3,3), 2),
            nn.BatchNorm2d(256),
            nn.LeakyReLU(),
            nn.Conv2d(256, 256, (3,3)),
            nn.LeakyReLU(),
        )

        self.flatten = nn.Flatten(start_dim=1)

        self.linearMap = nn.Sequential(
            nn.Linear(256 * 28 * 28, 2048),
            nn.LeakyReLU()
        )
        
    def forward(self, x):
        x = self.stageOneCNN(x)
        x = self.stageTwoCNN(x)
        x = self.stageThreeCNN(x)
        x = self.stageFourCNN(x)
        x = self.flatten(x)
        x = self.linearMap(x)
        return x

class Decoder(nn.Module):
    def __init__(self):
        super().__init__()

        self.linearMap = nn.Sequential(
            nn.Linear(2048, 256 * 28 * 28),
            nn.LeakyReLU()
        )

        self.unflatten = nn.Unflatten(dim=1, unflattened_size=(256,28,28))

        self.stageFourDeconv = nn.Sequential(
            nn.ConvTranspose2d(256, 256, (3,3)),
            nn.BatchNorm2d(256),
            nn.LeakyReLU(),
            nn.ConvTranspose2d(256, 128, (3,3), 2),
            nn.LeakyReLU(),
        )

        self.stageThreeDeconv = nn.Sequential(
            nn.ConvTranspose2d(128, 128, (3,3)),
            nn.BatchNorm2d(128),
            nn.LeakyReLU(),
            nn.ConvTranspose2d(128, 64, (3,3), 2, 1),
            nn.LeakyReLU()
        )

        self.stageTwoDeconv = nn.Sequential(
            nn.ConvTranspose2d(64, 64, (3,3)),
            nn.BatchNorm2d(64),
            nn.LeakyReLU()
        )

        self.stageTwoOutput = nn.ConvTranspose2d(64, 32, (3,3), 2, 1)

        self.stageOneDeconv = nn.Sequential(
            nn.ConvTranspose2d(32,32, (3,3)),
            nn.BatchNorm2d(32),
            nn.LeakyReLU()
        )

        self.stageOneOutput = nn.ConvTranspose2d(32,1,(3,3), 2, 1)

    def forward(self, x):
        x = self.linearMap(x)
        x = self.unflatten(x)
        x = self.stageFourDeconv(x)
        x = self.stageThreeDeconv(x)
        x = self.stageTwoDeconv(x)
        x = self.stageTwoOutput(x, output_size=(254,254))
        x = torch.nn.functional.leaky_relu(x)
        x = self.stageOneDeconv(x)
        x = self.stageOneOutput(x, output_size=(512,512))
        x = torch.nn.functional.leaky_relu(x)
        return x

class Nissl(Dataset):
    def __init__(self, images, labels=None, transform=None, target_transform=None):
        self.images = images
        self.transform = transform
        self.target_transform = target_transform
        self.labels = labels

    def __len__(self):
        return len(self.images)

    def __getitem__(self, idx):
        image = self.images[idx]
        if self.transform:
            image = self.transform(image)
        return image

    def getPath(self, idx):
        label = self.labels[idx]
        return label

# Get device
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
# Load models
encoder = Encoder()
decoder = Decoder()

encoder = nn.DataParallel(encoder)
decoder = nn.DataParallel(decoder)

encoder.to(device)
decoder.to(device)

# Setup params
paramsToOptimize = [
    {'params': encoder.parameters()},
    {'params': decoder.parameters()}
]

# Optimizer and Loss
optimizer = torch.optim.Adam(paramsToOptimize, lr=1e-3)
loss_fn = torch.nn.MSELoss()
def trainEpoch(epoch_index, tb_writer):
    running_loss = 0.
    last_loss = 0.
    # Here, we use enumerate(training_loader) instead of
    # iter(training_loader) so that we can track the batch
    # index and do some intra-epoch reporting
    for i, data in enumerate(trainingLoader):
        # Every data instance is an input + label pair
        inputs = data.to(device)
        # Zero your gradients for every batch!
        optimizer.zero_grad()

        # Make predictions for this batch
        encoded = encoder(inputs)
        decoded = decoder(encoded)
        # Compute the loss and its gradients
        loss = loss_fn(decoded, inputs)
        loss.backward()

        # Adjust learning weights
        optimizer.step()
        # Gather data and report
        running_loss += loss.item()
        if i % 100 == 99:
            last_loss = running_loss / 50 # loss per batch
            print('  batch {} loss: {}'.format(i + 1, last_loss))
            tb_x = epoch_index * len(trainingLoader) + i + 1
            tb_writer.add_scalar('Loss/train', last_loss, tb_x)
            running_loss = 0.

    return last_loss

def plot_ae_outputs(encoder,decoder,n=10):
    plt.figure(figsize=(16,4.5))
    for i in range(n):
      ax = plt.subplot(2,n,i+1)
      validationDataset = Nissl(validationAtlasImages, transform=transforms)
      img = validationDataset[i].to(device)
      img = img[None, :]
      encoder.eval()
      decoder.eval()
      with torch.no_grad():
        out = encoder(img)
        rec_img  = decoder(out)
      plt.imshow(img.cpu().squeeze().numpy(), cmap='gist_gray')
      ax.get_xaxis().set_visible(False)
      ax.get_yaxis().set_visible(False)  
      if i == n//2:
        ax.set_title('Original images')
      ax = plt.subplot(2, n, i + 1 + n)
      plt.imshow(rec_img.cpu().squeeze().numpy(), cmap='gist_gray')  
      ax.get_xaxis().set_visible(False)
      ax.get_yaxis().set_visible(False)  
      if i == n//2:
         ax.set_title('Reconstructed images')
    plt.show()   

if __name__ == '__main__':
    
    # Transformations on images
    transforms = transforms.Compose([transforms.ToTensor()])
    # Read the png locations
    nrrdPath = "C:/Users/Alec/.belljar/nrrd/png_half/"
    dapiPath = "C:/Users/Alec/.belljar/dapi/"
    fileList = os.listdir(nrrdPath) # path to flat pngs
    dapiList = os.listdir(dapiPath)
    absolutePaths = [nrrdPath + p for p in fileList]
    dapiAbsPaths = [dapiPath + p for p in dapiList]
    # Load all the images into memory
    allDAPI = [cv2.cvtColor(cv2.imread(p), cv2.COLOR_BGR2GRAY) for p in dapiAbsPaths]
    allSlices = [cv2.cvtColor(cv2.imread(p), cv2.COLOR_BGR2GRAY) for p in absolutePaths[:int(len(absolutePaths)*0.01)]] #[:int(len(absolutePaths)*0.05)]
    # Split this up into t and v
    trainingAtlasImages, validationAtlasImages = train_test_split(allSlices, test_size=0.2)
    trainingDAPIImages, validationDAPIImages = train_test_split(allDAPI, test_size=0.2)

    trainingDataset, validationDataset = Nissl(trainingDAPIImages + trainingAtlasImages, transform=transforms), Nissl(validationAtlasImages + validationDAPIImages, transform=transforms)
    # Now construct data loaders for batch training
    trainingLoader, validationLoader = DataLoader(trainingDataset, batch_size=4, shuffle=True), DataLoader(validationDataset, batch_size=4, shuffle=True)

    # Initializing in a separate cell so we can easily add more epochs to the same run
    # timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    # writer = tensorboard.SummaryWriter('runs/fashion_trainer_{}'.format(timestamp))
    # epoch_number = 0

    # EPOCHS = 10

    # best_vloss = float('inf')

    # for epoch in range(EPOCHS):
    #     print('EPOCH {}:'.format(epoch_number + 1))

    #     # Make sure gradient tracking is on, and do a pass over the data
    #     encoder.train()
    #     decoder.train()
    #     avg_loss = trainEpoch(epoch_number, writer)
    #     # We don't need gradients on to do reporting
    #     encoder.eval()
    #     decoder.eval()
    #     running_vloss = 0.0
    #     with torch.no_grad():
    #         for i, vdata in enumerate(validationLoader):
    #             vinputs = vdata.to(device)
    #             encoded = encoder(vinputs)
    #             decoded = decoder(encoded)
    #             vloss = loss_fn(decoded, vinputs)
    #             running_vloss += vloss

    #     avg_vloss = running_vloss / (i + 1)
    #     print('LOSS train {} valid {}'.format(avg_loss, avg_vloss))

    #     # Log the running loss averaged per batch
    #     # for both training and validation
    #     writer.add_scalars('Training vs. Validation Loss',
    #                     { 'Training' : avg_loss, 'Validation' : avg_vloss },
    #                     epoch_number + 1)
    #     writer.flush()

    #     # Track best performance, and save the model's state
    #     if avg_vloss < best_vloss:
    #         # plot_ae_outputs(encoder, decoder)
    #         best_vloss = avg_vloss
    #         model_path = '../models/predictor'.format(timestamp, epoch_number)
    #         torch.save(encoder.state_dict(), model_path+"_encoder.pt")
    #         torch.save(decoder.state_dict(), model_path+"_decoder.pt")

    #     epoch_number += 1

    encoder.load_state_dict(torch.load("../models/predictor_encoder.pt"))
    encoder.eval()
        
    # decoder.load_state_dict(torch.load("../models/predictor_decoder.pt"))
    # decoder.eval()

    # Code to make the atlas embeddings
    embeddings = {}
    with open("atlasEmbeddings.pkl","rb") as f:
        embeddings = pickle.load(f)
    
    dataset = Nissl(allDAPI[:52], transform=transforms, labels=dapiList[:52])
    similarity = {}
    for i in range(len(dataset)):
        img = dataset[i].to(device)
        img = img[None, :]
        encoder.eval()
        # Debug for verifying paths match the image we are processing
        # cv2.imshow("image from dataset", dataset[i].numpy().transpose(1, 2, 0))
        # cv2.imshow("image from filepaths", cv2.imread(nrrdPath + dataset.getPath(i)))
        # cv2.waitKey(0)
        with torch.no_grad():
            out = encoder(img).cpu().numpy()
            similarity[dataset.getPath(i)] = {}
            for name, e in embeddings.items():
                similarity[dataset.getPath(i)][name] = spatial.distance.correlation(out, e)
    
    # find the consensus angle
    consensus = {i:0 for i in range(-10,11,1)}
    for name, scores in similarity.items():
        ordered = sorted(scores, key=scores.get)
        angles = []
        for result in ordered[:3]:
            v = result.split("_")
            angles.append(int(v[2]))
        consensus[stats.mode(angles)[0][0]] += 1
    
    # select the best sections along that angle
    best = []
    idealAngle = max(consensus, key=consensus.get)
    for name, scores in similarity.items():
        ordered = sorted(scores, key=scores.get)
        for result in ordered:
            v = result.split("_")
            s = int(v[3].split(".")[0])
            if int(v[2]) == idealAngle:
                best.append(result)
                break

        
    for i, name in enumerate(best):
        print(dataset.getPath(i), name)
        
    # plot_ae_outputs(encoder, decoder)


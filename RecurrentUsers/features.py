import os
import random
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from data_eda import data_restaurants
import nltk
from nltk.tokenize import word_tokenize
from nltk.stem.porter import *
porter_stemmer = PorterStemmer()
sentence_tokenizer = nltk.data.load('tokenizers/punkt/english.pickle')
import itertools
# %% --------------------------------------- Set-Up --------------------------------------------------------------------
SEED = 42
np.random.seed(SEED)
random.seed(SEED)
TURN_BERT_INTO_SIMILARITY = False

# %% --------------------------------------- Behaviour Features --------------------------------------------------------
# Maximum Number of Reviews in the same day per Reviewer  -> Checked, it's correct
test12 = data_restaurants.groupby(['ReviewerID', 'Date']).count()
revz = [i[0] for i in test12.index]
revz = list(set(revz))
maxList = [test12.loc[i]['ReviewID'].max() for i in revz]
max_dict = {}
for Id in range(len(revz)):
    max_dict[revz[Id]] = maxList[Id]
new_thing = data_restaurants['ReviewerID'].apply(lambda x: max_dict[x])
data_restaurants['MNR'] = new_thing

# Average Review Length per Reviewer --> Checked, it's correct
data_restaurants['WC'] = data_restaurants['Review'].apply(lambda x: len(x.split(' ')))
word_avg = data_restaurants.groupby('ReviewerID').mean()['WC']
data_restaurants['avg_revL'] = data_restaurants['ReviewerID'].apply(lambda x: word_avg[x])

# Percentage of 4-5 star-reviews per user  --> Checked, it's correct
data_restaurants['posR'] = data_restaurants['Rating'].apply(lambda x: 1 if x >= 4 else 0)
posR = data_restaurants.groupby('ReviewerID').mean()['posR']
data_restaurants['avg_posR'] = data_restaurants['ReviewerID'].apply(lambda x: posR[x])

# Reviewer Deviation  -> A bit trickier to check but it looks correct, and I also interpreted it this way
ProdPivot = data_restaurants.pivot_table(index='Date', columns='ProductID', values='Rating')
avProdR = ProdPivot.mean()
data_restaurants['exp_Product_Rating'] = data_restaurants['ProductID'].apply(lambda x: avProdR[x])
data_restaurants['abs_prod_rating_dev'] = np.abs(data_restaurants['Rating'] - data_restaurants['exp_Product_Rating'])
exp_rev_frame = data_restaurants.groupby('ReviewerID').mean()['abs_prod_rating_dev']
data_restaurants['Reviewer_deviation'] = data_restaurants['ReviewerID'].apply(lambda x: exp_rev_frame[x])




def cosine_similarity(document_1_data, document_2_data):
    document_vector_word_index = [] # here fill this with an ordered list of all the unique words across both documents
    d1_uniqs = []
    d1_nun = []
    dat = sentence_tokenizer.tokenize(document_1_data)
    for sent in dat:
        d1_uniqs.extend(word_tokenize(sent))
        d1_nun.extend(word_tokenize(sent))
        d1_uniqs = list(set(d1_uniqs))
    d2_uniqs = []
    d2_nun = []
    dat2 = sentence_tokenizer.tokenize(document_2_data)
    for sent in dat2:
        d2_uniqs.extend(word_tokenize(sent))
        d2_uniqs = list(set(d2_uniqs))
        d2_nun.extend(word_tokenize(sent))

    
    all_words = d1_nun+d2_nun   

    overlap = d1_uniqs + d2_uniqs 
    # so this is all of the unique words across the two documents
    document_vector_word_index += list(set(overlap))
    

    document_1_vector = list(np.zeros(len(document_vector_word_index)))  # fill in the array with the frequency of the words in the document
    document_2_vector = list(np.zeros(len(document_vector_word_index))) # fill in the array with the frequency of the words in the document

    for wOrd in d1_nun:
        document_1_vector[document_vector_word_index.index(wOrd)] +=1
    
    for wOrd in d2_nun:
        document_2_vector[document_vector_word_index.index(wOrd)] +=1
    
    d1_norm = (np.sum(np.array(document_1_vector)**2))**(1/2)
    d2_norm = (np.sum(np.array(document_2_vector)**2))**(1/2)
    
    cosSim = np.dot(document_1_vector,document_2_vector)/(d1_norm*d2_norm)


    
    return (cosSim)
countR2 = data_restaurants.groupby('ReviewerID').count().index
data_restaurants['stem_rev'] = data_restaurants['Review'].apply(lambda x: porter_stemmer.stem(x)) 
cos_dict = {}
print('doin cosine')
for x in countR2:
    temp = data_restaurants[data_restaurants['ReviewerID'] == x]
    cands = []
    for i in itertools.combinations(temp.index,2):
        cands.append(cosine_similarity(temp.loc[i[0]]['stem_rev'],temp.loc[i[1]]['stem_rev']))
    cos_dict[x]=max(cands)
print('done cosine')
data_restaurants['max_cos'] = data_restaurants['ReviewerID'].apply(lambda x: cos_dict[x])


x = data_restaurants.drop(["Fake"], axis=1)
y = data_restaurants["Fake"].replace("N", 0).replace("Y", 1)
x_train, x_test, y_train, y_test = train_test_split(x, y, random_state=SEED, test_size=0.3, stratify=y)

if TURN_BERT_INTO_SIMILARITY:
    features_behaviour_train, features_behaviour_test = x_train, x_test
else:
    features_behaviour_train = x_train[['Reviewer_deviation', 'avg_posR', 'avg_revL', 'MNR','max_cos']]
    features_behaviour_test = x_test[['Reviewer_deviation', 'avg_posR', 'avg_revL', 'MNR','max_cos']]

# %% ----------------------------------------- BERT Features -----------------------------------------------------------
SEQ_LEN = 100
N_LAYERS = 4
N_FEATURES = 3

features_bert_train = np.load("saved_features_BERT_sigmoid/features_train_{}layers_{}features_{}len.npy".format(N_LAYERS, N_FEATURES, SEQ_LEN))
features_bert_test = np.load("saved_features_BERT_sigmoid/features_test_{}layers_{}features_{}len.npy".format(N_LAYERS, N_FEATURES, SEQ_LEN))
print("BERT cls bias and weights:")
with open("saved_models_BERT_sigmoid/BERT_last_weights{}layers_{}features_{}len.txt".format(N_LAYERS, N_FEATURES, SEQ_LEN), "r") as s:
    print(s.read())

# Inverse-Standardizing here because R/JAGS is stupid
# JAGS will do x - mu / std, so here we do x * std + mu
features_bert_train_mu = np.mean(features_bert_train, axis=0)
features_bert_train_std = np.std(features_bert_train, axis=0)
features_bert_train = features_bert_train * features_bert_train_std + features_bert_train_mu
features_bert_test = features_bert_test * features_bert_train_std + features_bert_train_mu

# This is a check to make sure the split made here for the Behaviour features matches the one made for BERT on BERT_features.py
# import torch
# import torch.nn as nn
# from transformers.modeling_bert import BertForSequenceClassification
# from transformers.tokenization_bert import BertTokenizer
# tokenizer = BertTokenizer.from_pretrained("bert-base-uncased")
#
# class BERTForFeatures(nn.Module):
#     def __init__(self, n_bert_layers=N_LAYERS, n_features=N_FEATURES, extract_features=False):
#         super(BERTForFeatures, self).__init__()
#         self.extract_features = extract_features
#         self.bert = BertForSequenceClassification.from_pretrained("bert-base-uncased")
#         self.bert.bert.encoder.layer = self.bert.bert.encoder.layer[:n_bert_layers]
#         self.bert.classifier = nn.Linear(768, n_features)
#         self.cls = nn.Linear(n_features, 2)
#
#     def forward(self, p, attn_mask):
#         features, *_ = self.bert(p, attention_mask=attn_mask)
#         if self.extract_features:
#             return features
#         return self.cls(features)
#
# model = BERTForFeatures(extract_features=True)
# model.load_state_dict(torch.load("saved_models_BERT/BERT_{}layers_{}features_{}len.pt".format(N_LAYERS, N_FEATURES, SEQ_LEN)))
# model.eval()
#
# x, x_mask = [], []
# for review in x_train["Review"].values[10:11]:
#     token_ids = tokenizer.convert_tokens_to_ids(tokenizer.tokenize(review)[:SEQ_LEN-2])
#     token_ids = [101] + token_ids + [102]
#     n_ids = len(token_ids)
#     attention_mask = [1] * n_ids
#     if n_ids < SEQ_LEN:
#         token_ids += [0] * (SEQ_LEN - n_ids)
#         attention_mask += [0] * (SEQ_LEN - n_ids)
#     x.append(token_ids)
#     x_mask.append(attention_mask)
# x, x_mask = torch.LongTensor(x), torch.FloatTensor(x_mask)
#
# with torch.no_grad():
#     feats = model(x, x_mask).numpy()
# print(feats, features_bert_train[10])
# # They are the same, good!

# %% ----------------------------------------- Combine Features --------------------------------------------------------
features_and_target_train = np.hstack((features_behaviour_train, features_bert_train, y_train.values.reshape(-1, 1)))
features_and_target_test = np.hstack((features_behaviour_test, features_bert_test, y_test.values.reshape(-1, 1)))

def dot_product(data):
    if len(data) < 2:
        data["BERTSimilarity"] = "Mmm"
    else:
        data["BERTSimilarity"] = abs(data[["fBERT{}".format(i) for i in range(N_FEATURES)]].values[0].dot(
            data[["fBERT{}".format(i) for i in range(N_FEATURES)]].values[1:].T).mean())
    return data

if "prep_data" not in os.listdir():
    os.mkdir("prep_data")
data_train = pd.DataFrame(
    features_and_target_train,
    columns=list(features_behaviour_train.columns) + ["fBERT{}".format(i) for i in range(N_FEATURES)] + ["Fake"]
)
data_test = pd.DataFrame(
    features_and_target_test,
    columns=list(features_behaviour_test.columns) + ["fBERT{}".format(i) for i in range(N_FEATURES)] + ["Fake"]
)
if TURN_BERT_INTO_SIMILARITY:
    data_train = data_train.groupby(["ReviewerID"]).apply(dot_product)
    data_test = data_test.groupby(["ReviewerID"]).apply(dot_product)
    # data_train_nonan = data_train.replace("Mmm", np.NaN).dropna()  # By doing this we see that most reviews are
    # import matplotlib.pyplot as plt  # with very small values, thus we give 0.1 to the new users
    # plt.hist(data_train_nonan["BERTSimilarity"].values, bins=20)
    # plt.show()
    data_train.replace("Mmm", 0.1, inplace=True)
    data_test.replace("Mmm", 0.1, inplace=True)
    data_train = data_train[['Reviewer_deviation', 'avg_posR', 'avg_revL', 'MNR', "BERTSimilarity", "Fake"]]
    data_test = data_test[['Reviewer_deviation', 'avg_posR', 'avg_revL', 'MNR', "BERTSimilarity", "Fake"]]

data_train.to_csv("prep_data/data_train.csv")
data_test.to_csv("prep_data/data_test.csv")

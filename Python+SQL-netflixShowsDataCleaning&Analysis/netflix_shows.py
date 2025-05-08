#!/usr/bin/env python
# coding: utf-8

# In[2]:


import kaggle
get_ipython().system('kaggle datasets files shivamb/netflix-shows')


# In[7]:


get_ipython().system('kaggle datasets download shivamb/netflix-shows')


# In[8]:


import zipfile
with zipfile.ZipFile("netflix-shows.zip") as ref:
    ref.extractall()


# In[3]:



import pandas as pd
df = pd.read_csv("netflix_titles.csv")
df.head()


# In[8]:


import sqlalchemy as sal
engine = sal.create_engine('mssql://HimaSumaDinesh/master?driver=ODBC+DRIVER+17+FOR+SQL+SERVER')
conn=engine.connect()
df.to_sql("df_netflix_raw",conn,index=False,if_exists='append')


# In[5]:



max(df.cast.dropna().str.len())


# In[10]:


df.isna().sum()


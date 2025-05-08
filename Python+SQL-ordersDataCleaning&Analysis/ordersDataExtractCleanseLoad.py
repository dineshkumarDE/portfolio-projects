#!/usr/bin/env python
# coding: utf-8

# In[3]:


pip install kaggle


# In[6]:


import kaggle
get_ipython().system('kaggle datasets files ankitbansal06/retail-orders')


# In[14]:


get_ipython().system('kaggle datasets download ankitbansal06/retail-orders')


# In[18]:


import zipfile
with zipfile.ZipFile("retail-orders.zip") as ref:
   ref.extractall()


# In[21]:


import pandas as pd
df = pd.read_csv("orders.csv")
df.head()


# In[22]:


df["Ship Mode"].unique()


# In[23]:


#add 'Not Available', 'unknown' as nan values while reading csv
df = pd.read_csv("orders.csv",na_values=['Not Available', 'unknown'])
df["Ship Mode"].unique()


# In[24]:


#rename columns with underscore and lowercase
df.columns


# In[34]:


df.columns=df.columns.str.lower().str.replace(" ","_")
df.columns


# In[40]:


#profit calculation

df["discount"]=df["list_price"]*df["discount_percent"]*0.01
df["sale_price"]=df["list_price"]-df["discount"]
df["profit"]=df["sale_price"]-df["cost_price"]
df.head()


# In[51]:


#change datatype of order_date to datetime
df["order_date"]=pd.to_datetime(df["order_date"],format ='%Y-%m-%d')


# In[62]:


#drop cost price list price and discount percent columns
df.drop(['list_price','cost_price','discount_percent'],axis=1,inplace=True)


# In[63]:


#load the data into sql server using replace option
import sqlalchemy as sal
engine = sal.create_engine('mssql://HimaSumaDinesh/master?driver=ODBC+DRIVER+17+FOR+SQL+SERVER')
conn=engine.connect()


# In[65]:


df.to_sql("df_orders",conn,index=False,if_exists='append')


# In[68]:


df.head()


#!/usr/bin/env python
# coding: utf-8

# In[6]:


import os
file_path = 'D:/Dinesh/end to end projects/Yelp-JSON/Yelp JSON/yelp_dataset/yelp_academic_dataset_review.json'


# In[11]:


size=os.path.getsize(file_path)
size_in_gb=size/1024/1024/1024
print(f"file size:{size_in_gb:.2f}GB")


# In[13]:


import json
num_split=25
# Read first 5 JSON objects (lines)
with open(file_path, 'r') as f:
    for i, line in enumerate(f):
        if i == 5:
            break
        try:
            record = json.loads(line)
            print(record)
        except json.JSONDecodeError:
            print(f"Invalid JSON on line {i + 1}")


# In[17]:


with open(file_path,'r',encoding='utf8') as f:
    total_lines = sum(1 for _ in f)

lines_per_file=total_lines//num_split
print(lines_per_file)


# In[19]:


print(f'total number of lines in file:{total_lines}  Number of lines per split:{lines_per_file}')


# In[20]:


print(os.getcwd())


# In[24]:


with open(file_path,'r',encoding='utf8') as f:
    for i in range(num_split):
       out_file = f"split_file_{i+1}.json"
        
       with open(out_file ,'w',encoding='utf8') as g:
         for j in range(lines_per_file):
           line_to_be_loaded = f.readline()
           if not line_to_be_loaded:
              break;
           g.write(line_to_be_loaded)
        


# In[31]:


import glob
files_created = glob.glob('D:/Dinesh/end to end projects/*.json')
for i,file in enumerate(files_created):
    size_in_mb = os.path.getsize(file)/1024/1024
    with open(file,'r',encoding='utf8') as f:
         num_lines = sum(1 for _ in f)
    print(f"number_of_lines in {file} is: {num_lines} and the size is :{size_in_mb:.2f}MB")


# In[33]:


pip install snowflake


# In[38]:





# In[ ]:






ELT Project:

This project involves downloading netflix shows dataset from kaggle API and store it into mssql server . 

Execute below cleansing activities on the data
--handling foreign char
--handling duplicates
--new table for listed_in,director, country,cast
--data type conversions for date added 
--populate missing values in country,duration columns



Do below data analysis on the cleansed data
--1  for each director count the no of movies and tv shows created by them in separate columns 
for directors who have created tv shows and movies both 
--2 which country has highest number of comedy movies 
--3 for each year (as per date added to netflix), which director has maximum number of movies released
--4 what is average duration of movies in each genre
--5  find the list of directors who have created horror and comedy movies both.
-- display director names along with number of comedy and horror movies directed by them 

-- Load reviews data
create or replace table yelp_reviews (review_text variant)

copy into yelp_reviews
from 's3://mydataenglearn/'
credentials =(
AWS_KEY_ID ='****'
AWS_SECRET_KEY='***'
)
FILE_FORMAT =(TYPE =JSON)

--Load businesses data
create or replace table yelp_businesses (business_text variant)

copy into yelp_businesses
from 's3://mydataenglearn/business/'
credentials =(
AWS_KEY_ID ='****'
AWS_SECRET_KEY='****'
)
FILE_FORMAT =(TYPE =JSON)

select * from yelp_businesses limit 10;

--Create a python UDF 

CREATE OR REPLACE FUNCTION analyze_sentiment(text STRING)
RETURNS STRING
LANGUAGE PYTHON
RUNTIME_VERSION = '3.8'
PACKAGES = ('textblob') 
HANDLER = 'sentiment_analyzer'
AS $$
from textblob import TextBlob
def sentiment_analyzer(text):
    analysis = TextBlob(text)
    if analysis.sentiment.polarity > 0:
        return 'Positive'
    elif analysis.sentiment.polarity == 0:
        return 'Neutral'
    else:
        return 'Negative'
$$;

--test the function
select  analyze_sentiment('i love snowflake')

--convert datatype from json and load required columns into tables
create table tbl_yelp_reviews as 
select review_text:business_id::string as business_id ,
review_text:date::date as review_date,
review_text:user_id::string as user_id,
review_text:stars::number as star,
review_text:text::string as review_msg,
analyze_sentiment(review_msg) as sentiment_analysis
 from yelp_reviews;

 select * from tbl_yelp_reviews limit 100


 


create or replace table sel * from tbl_yelp_businesses as 
select business_text:business_id::string as business_id
,business_text:name::string as name
,business_text:city::string as city
,business_text:state::string as state
,business_text:review_count::string as review_count
,business_text:stars::number as stars
,business_text:categories::string as categories
from yelp_businesses



select * from tbl_yelp_businesses


--Analysis questions

-- 1.number of businesses in each category
with cte as (
select business_id,trim(category_split.value) as category 
from tbl_yelp_businesses 
,lateral split_to_table(categories,',') as category_split
) select category,count(*) as number_of_business 
from cte 
group by 1
order by 2 desc

--2 . top 10 users who have reviewed the most businesses in "restauarants" category
select r.user_id,count(distinct b.business_id) from tbl_yelp_reviews r
inner join
tbl_yelp_businesses b
on r.business_id = b.business_id
and b.categories ilike '%restaurants%'
group by 1 
order by 2 desc
limit 10

--3 find mostpopular categories of business based on reviews

with cte as (
select business_id,trim(category_split.value) as category 
from tbl_yelp_businesses 
,lateral split_to_table(categories,',') as category_split
)

select c.category,count(r.business_id) as num_reviews from cte c inner join tbl_yelp_reviews r
on c.business_id=r.business_id 
group by 1 
order by 2 desc



--4 find top 3 most recent reviews for each business
select business_id,review_msg,review_date 
,row_number() over (partition by business_id order by review_date desc) as rn
from tbl_yelp_reviews
qualify rn<=3


--5 find month with highest number of reviews
select month(review_date) as review_month,count(*) as number_of_reviews 
from tbl_yelp_reviews
group by 1
order by 2 desc
limit 1


--6 find percentage of 5* review for each business
--Rw8Zf_snPdZO_B3XFOsJ6w	59.05

select r.business_id,cast (count(case when star=5 then 1 else null end)*100.00/count(*) as decimal(5,2)) as fivestarpercent
from tbl_yelp_reviews r 
group by 1

--7 find top 5 most reviewed business in each city
with cte as (
select b.city,b.business_id,count(*) as review_cnt
from tbl_yelp_businesses b
inner join tbl_yelp_reviews r
on b.business_id=r.business_id
group by 1,2)
select * from cte 
qualify row_number() over (partition by city order by review_cnt desc) <6

--8 average rating of business having atleast 100 reviews

select business_id,count(*) as num_reviews,avg(star) as average_rating from tbl_yelp_reviews 
group by 1
having num_reviews>=100

--9 list top 10 users who have written most reviews along with the business whch they have reviewed
with cte as (select user_id ,count(*) as num_reviews
from tbl_yelp_reviews
group by 1
order by num_reviews desc
limit 10)
select c.user_id,r.business_id from cte c inner join tbl_yelp_reviews r
on c.user_id = r.user_id
group by 1 ,2 
order by 1,2


--10 find top 10 business with highest positive sentiment reviews
select business_id,count(*) as positive_review_cnt
from tbl_yelp_reviews
where sentiment_analysis ='Positive'
group by 1 
order by positive_review_cnt desc
limit 10

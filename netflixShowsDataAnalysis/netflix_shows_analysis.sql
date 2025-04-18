
-- data cleansing ----------------------------------------------------------
select * from df_netflix_raw where show_id='s5023'

create TABLE [dbo].[df_netflix_raw](
	[show_id] [varchar](10) primary key,
	[type] [varchar](10) NULL,
	[title] [nvarchar](200) NULL,
	[director] [varchar](250) NULL,
	[cast] [varchar](1000) NULL,
	[country] [varchar](150) NULL,
	[date_added] [varchar](20) NULL,
	[release_year] [bigint] NULL,
	[rating] [varchar](10) NULL,
	[duration] [varchar](10) NULL,
	[listed_in] [varchar](100) NULL,
	[description] [varchar](500) NULL
)

-- handling foreign char
--used nvarchar for title
select * from df_netflix_raw where show_id='s5023'


--handling duplicates
select show_id from df_netflix_raw group by show_id having count(*)>1 --no duplicates

select * from df_netflix_raw where concat(title,type) in (select concat(title,type) from df_netflix_raw group by title,type having count(*)>1 ) order by title -- 3duplicates

with rndata as 
(select *,row_number() over (partition by title,type order by show_id desc) as rn from df_netflix_raw)
select * from rndata where rn =1 --remove duplicates


--new table for listed_in,director, country,cast
drop table if exists netflix_director;
select show_id,trim(value) as director
into netflix_director
from df_netflix_raw
cross apply string_split(director,',');

drop table if exists netflix_cast;
select show_id,value as cast
into netflix_cast
from df_netflix_raw
cross apply string_split(cast,',');

drop table if exists netflix_genre;
select show_id,trim(value) as genre 
into netflix_genre
from df_netflix_raw
cross apply string_split(listed_in,',');

drop table if exists netflix_country;
select show_id,trim(value)  as country
into netflix_country
from df_netflix_raw
cross apply string_split(country,',');

--data type conversions for date added 

with rndata as 
(select *,row_number() over (partition by title,type order by show_id desc) as rn from df_netflix_raw)
select show_id,type,title,cast(date_added as date) as date_added ,release_year,duration,description from rndata

--populate missing values in country,duration columns
insert into netflix_country
select r.show_id,m.country
from
df_netflix_raw r
inner join
(select director,country
from netflix_director d 
inner join netflix_country c
on d.show_id = c.show_id
group by director,country) m
on r.director=m.director
where r.country is null




with rndata as 
(select *,row_number() over (partition by title,type order by show_id desc) as rn from df_netflix_raw)
select show_id,type,title,cast(date_added as date) as date_added ,release_year,rating,case when duration is null then rating else duration end as duration,description 
into netflix_land
from rndata 
------------------------------------------------------------------------------------------------------

---data analysis----------------------------

/*1  for each director count the no of movies and tv shows created by them in separate columns 
for directors who have created tv shows and movies both */


select d.director , 
sum(CASE WHEN n.type='movie' then 1 else 0 end) as num_movies,
sum(CASE WHEN n.type='tv show' then 1 else 0 end) as num_tv_shows
from netflix_land n
inner join netflix_director d
on n.show_id = d.show_id
group by director
having count(distinct type) =2


select d.director , 
count(distinct CASE WHEN n.type='movie' then n.show_id end) as num_movies,
count(distinct CASE WHEN n.type='tv show' then n.show_id end) as num_tv_shows
from netflix_land n
inner join netflix_director d
on n.show_id = d.show_id
group by director
having count(distinct type) =2


--2 which country has highest number of comedy movies 
select top 1 country,count(distinct g.show_id) as num_comedy
from netflix_genre g inner join
netflix_country c
on g.show_id = c.show_id 
inner join netflix_land l
on c.show_id=l.show_id
and l.type='movie'
where genre='comedies'
group by country
order by num_comedy desc


--3 for each year (as per date added to netflix), which director has maximum number of movies released


with cte as (
select d.director,
year(date_added) as release_year,count(distinct l.show_id) as num_movies
from netflix_land l
inner join netflix_director d
on l.show_id = d.show_id
and l.type='movie'
group by d.director,year(date_added))
,cte2 as 
(select director,release_year,num_movies,ROW_NUMBER() over (partition by release_year order by num_movies desc,director) as rn from cte)
select * from cte2 where rn=1




--4 what is average duration of movies in each genre
select genre,avg(cast(replace(duration,' min','') as int)) as avg_duration
from netflix_land l
inner join netflix_genre g
on l.show_id=g.show_id
and l.type='movie'
group by genre

--5  find the list of directors who have created horror and comedy movies both.
-- display director names along with number of comedy and horror movies directed by them 

select director,
count(distinct case when genre='comedies' then l.show_id end) as num_com_movies,
count(distinct case when genre='horror movies' then l.show_id end) as num_horror_movies from 
netflix_director d inner join 
netflix_genre g
on d.show_id=g.show_id
inner join netflix_land l
on l.show_id=d.show_id
and l.type='movie'
where genre in ('comedies','horror movies')
group by director
having count(distinct genre) >1
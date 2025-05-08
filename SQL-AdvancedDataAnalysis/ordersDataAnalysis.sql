--1 Find top 1 outlets by cuisine type w/o using limit and top function
--query 1
with top_restaurants as (
select cuisine,restaurant_id,count(*) as no_of_orders
from orders group by cuisine,restaurant_id
),
rank_restaurants as(
select *,ROW_NUMBER() over (partition by cuisine order by no_of_orders desc) as restaurant_rank
from top_restaurants)
select * from rank_restaurants where restaurant_rank=1

--query2

with top_restaurants as (
select cuisine,restaurant_id,count(*) as no_of_orders
from orders group by cuisine,restaurant_id
)
select * from (
select *,ROW_NUMBER() over (partition by cuisine order by no_of_orders desc) as restaurant_rank
from top_restaurants)a where a.restaurant_rank=1


--2 Find the daily new customer count from the launch date (everyday how many new customers are we acquiring)
with dist_cust as(
select customer_code as dist_customers,min(cast(placed_At  as date)) as  min_order_date from orders group by customer_code)
select min_order_date as order_dt,count(dist_customers) as new_cust_count from dist_cust group by min_order_date order by order_dt


--3 count of all users who were aquired in Jan 2025 and only placed one order in Jan and they didnt place any other order
with cte as (
select customer_code,min(cast(placed_at as date)) as min_order_date,max(cast(placed_at as date)) as max_order_date,count(*) as order_cnt  from orders group by customer_code 
)select count(*) as user_count from cte where month(min_order_date)=1 and month(max_order_date)=1 and order_cnt =1 and year(min_order_date)=2025


--4 :List all customers with no order in the last 7 days but were acquired one month ago with their first order on promo

with cte as 
(select customer_code,min(cast(placed_at as date)) as min_order_date,max(cast(placed_at as date)) as max_order_date from orders group by customer_code 
)select * from cte c
inner join orders o
on c.customer_code = o.customer_code
and c.min_order_date = cast(o.placed_at as date)
and o.promo_code_name is not null
where c.max_order_date < dateadd(day,-7,cast('2025-03-31' as date)) and min_order_date <    dateadd(month,-1,cast('2025-03-31' as date))


--5 growth team is planning to create a trigger that will target customers after their every third order with a personalized communicaation nd they have asked you to create a query for this
--query 1
select customer_code,count(*) as number_of_orders  from orders group by customer_code having count(*)%3=0 and max(cast(placed_at as date)) = cast('2025-03-31' as date)

--query2
with cte as (
select *,
ROW_NUMBER() over(partition by customer_code order by placed_at) as rn
from orders)
select * from cte where rn%3=0 and cast(placed_at as date) = cast('2025-03-31' as date)


--6 list customers who placed more than one order and all their orders on a promo only
--query1

select customer_code from orders o 
where not EXISTS (SELECT 1 FROM orders po where po.customer_code=o.customer_code and po.promo_code_name is null)
group by customer_code having count(*)>1

--query2
select customer_code ,count(*) as order_cnt, count(promo_code_name) as promo_count
from orders
group by customer_code
having count(*)>1 and count(*)=count(promo_code_name)

--7 what percent of users were organically acquired in jan 2025 (placed their first order without promo code)
 
--query 1
with cte as (
select customer_code, min(cast(placed_at as date)) as min_order_dt ,min(promo_code_name) as first_promo
from orders group by customer_code)
select cast((count(c.customer_code) *100.00) /count(c1.customer_code) as decimal(4,2)) as user_percent from cte c1
left outer join cte c
on c.customer_code=c1.customer_code
and month(c.min_order_dt) = 1 and year(c.min_order_dt)=2025 and c.first_promo is null


--query2
with cte as(
select *,ROW_NUMBER() over(partition by customer_code order by placed_at) as rn from orders where month(placed_at)=1)
select cast(count(case when rn=1 and promo_code_name is null then customer_code end)*100.0 /count(distinct customer_code) as decimal(4,2)) as user_percent
from cte 
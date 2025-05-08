--select * from df_orders


--CREATE TABLE [dbo].[df_orders](
--	[order_id] int primary key,
--	[order_date] date,
--	[ship_mode] varchar(20),
--	[segment] varchar(20),
--	[country] varchar(20),
--	[city] varchar(20),
--	[state] varchar(20),
--	[postal_code] int,
--	[region] varchar(20),
--	[category] varchar(20),
--	[sub_category] varchar(20),
--	[product_id] varchar(50) ,
--	[quantity] int,
--	[discount] decimal(7,2),
--	[sale_price] decimal(7,2),
--	[profit] decimal(7,2))

	--top 10 revenue generating product id


	select top 10 product_id,sum(sale_price) as revenue
	from df_orders
	group by product_id
	order by revenue desc

	
	--find top 5 highest selling products in each region
	with revenuecte as (
	select product_id,region,
	sum(sale_price) as revenue
	from df_orders
	group by product_id,region
	)
    select * from(
	select *,
	rank() over (partition by region order by revenue desc) as rk
	from revenuecte)a where rk <=5


	--find month over month growth comparison for 2022 and 2023 sales eg : jan 2022 vs jan 2023

	with yearcte as (
	select year(order_date) as yr,month(order_date) as mn,sum(sale_price) as revenue
	from df_orders
	group by year(order_date),month(order_date))
	select mn , 
	sum( case when yr = '2022' then revenue else 0 end) as "2022_growth",
	sum( case when yr = '2023' then revenue else 0 end) as "2023_growth"
	from yearcte 
	group by mn
	order by mn


	--for each category which month had highest sales

	with catrevcte as (
	select category,format(order_date,'yyyyMM') as mn,sum(sale_price) as rev from df_orders
	group by category,format(order_date,'yyyyMM'))
	select * from (
	select *
	,rank() over (partition by category,mn order by rev desc) as rnk from catrevcte)a where rnk =1



	--which sub category had highest growth by profit in 2023 compare to 2022
	select * from df_orders


with profitadd as (
select sub_category,year(order_date) as yr,sum(profit) pg from df_orders group by sub_category,year(order_date))
,yearcomp as
(select sub_category,
sum(case when yr = 2022 then pg else 0 end )as profit_2022,
sum(case when yr = 2023 then pg else 0 end )as profit_2023
from profitadd
group by sub_category)

select top 1 sub_category , profit_2023-profit_2022 as profit_growth
from yearcomp
order by profit_2023-profit_2022 desc



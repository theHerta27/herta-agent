# 结算项目

只用Python标准库。金额单位为整数分，折扣为0到100的整数百分比；整数除法向下取整。
商品小计=sum(单价×数量)；折扣后达到5000分免运费，否则运费500分。
保留checkout返回的subtotal/discount/shipping/total字段。
测试在tests，使用unittest；不能修改或删除现有测试，不装依赖。

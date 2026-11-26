# backend/scripts/seed_data.py
"""种子数据：意图体系+ 演示用户/商品/订单"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Intent, User, Product, Order
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# 意图体系（NLU 意图分类体系：3 大类 18 个意图）
INTENTS = [
    # 业务咨询类 intent_001~007
    ('商品咨询', 'product_inquiry', 'rag', '商品价格、参数、库存、好坏等咨询', 5,
     '这个商品多少钱;有什么产品推荐;手机怎么样;耳机有货吗'),
    ('促销活动', 'promotion', 'rag', '平台促销、打折、满减活动咨询', 4,
     '有什么促销活动;现在打折吗;满减怎么算;618有什么优惠'),
    ('配送时效', 'shipping', 'rag', '物流配送时间、运费、包邮政策', 5,
     '几天能到;运费多少;包邮吗;发货时间是什么时候'),
    ('支付问题', 'payment', 'rag', '支付方式、付款失败、发票问题', 6,
     '支持微信支付吗;付款失败怎么办;能开发票吗;货到付款'),
    ('优惠券使用', 'coupon', 'rag', '优惠券领取、使用、抵扣规则', 4,
     '优惠券怎么领;券怎么用;红包能叠加吗'),
    ('会员权益', 'member', 'rag', '会员等级、积分、专属权益', 3,
     '会员有什么权益;积分怎么兑换;怎么升级会员'),
    ('售后政策', 'after_sale', 'rag', '保修、维修、七天无理由等售后政策', 6,
     '保修多久;商品坏了怎么办;七天无理由退货;质量有问题怎么处理'),
    # 订单服务类 intent_100~106
    ('订单查询', 'order_query', 'tool', '查询订单状态、详情', 8,
     '查一下我的订单;我的订单到哪了;什么时候发货;查订单'),
    ('订单修改', 'order_modify', 'tool', '修改订单信息', 8,
     '我想改订单;订单信息填错了;改收货人'),
    ('取消订单', 'cancel_order', 'tool', '取消未发货订单', 9,
     '取消订单;我不想要了;帮我撤单'),
    ('申请退款', 'refund_request', 'tool', '退款、退货申请与进度', 10,
     '我要退款;怎么退货;退款进度查询;退钱'),
    ('物流追踪', 'logistics_track', 'tool', '物流单号、配送轨迹查询', 8,
     '物流到哪了;快递单号是多少;货到什么地方了'),
    ('催促发货', 'urge_shipping', 'tool', '催促商家尽快发货', 7,
     '怎么还不发货;催一下发货;等了好几天了'),
    ('修改地址', 'modify_address', 'tool', '修改收货地址', 8,
     '改一下收货地址;地址写错了;换个地址'),
    # 投诉建议类 intent_200~203
    ('投诉', 'complaint', 'transfer', '对商品、服务、物流的投诉', 10,
     '我要投诉;你们服务太差了;给我个说法;骗子'),
    ('退款退货纠纷', 'refund_dispute', 'transfer', '退款退货产生的纠纷', 10,
     '退款太慢了;你们不给我退货我就投诉;退款被拒绝了'),
    ('建议反馈', 'suggestion', 'llm', '对平台的建议和反馈', 5,
     '我有个建议;希望改进一下;反馈个问题'),
    ('人工客服', 'human_agent', 'transfer', '要求转接人工客服', 10,
     '转人工;我要人工客服;找真人;人工服务'),
]

# 演示用户
DEMO_USERS = [
    dict(username='demo_user', phone='13800138000', email='demo@example.com',
         password_hash='demo', user_type='customer'),
    dict(username='张女士', phone='13912345678', password_hash='demo', user_type='customer'),
]

# 演示商品
DEMO_PRODUCTS = [
    dict(name='无线降噪耳机 Pro', category='数码配件', price=799.00, stock=156, sales=2300,
         promotion='限时直降100元', description='主动降噪，40小时续航，蓝牙5.3，Type-C快充'),
    dict(name='智能手表 S6', category='数码配件', price=1299.00, stock=88, sales=1500,
         promotion='晒单返50元红包', description='AMOLED 高清屏，血氧心率监测，14天超长续航，50米防水'),
    dict(name='便携保温杯 500ml', category='家居生活', price=129.00, stock=430, sales=8600,
         promotion='第二件半价', description='316不锈钢内胆，12小时保温，一键开合，防漏设计'),
    dict(name='轻弹力运动鞋', category='运动服饰', price=499.00, stock=210, sales=3200,
         promotion=None, description='轻量缓震鞋底，透气飞织鞋面，适合跑步健身日常穿搭'),
    dict(name='机械键盘 87键', category='数码配件', price=399.00, stock=0, sales=5400,
         promotion='到货通知', description='热插拔轴体，RGB背光，三模连接，PBT键帽'),
    dict(name='多功能空气炸锅 5L', category='厨房电器', price=349.00, stock=95, sales=4100,
         promotion='满300减40', description='5升大容量，360°热风循环，8大预设菜单，可拆洗不粘内胆'),
]

# 演示订单（挂在 demo_user 下）
DEMO_ORDERS = [
    dict(order_no='ORDER20260815001', status='shipped', product_name='无线降噪耳机 Pro',
         quantity=1, total_amount=799.00, payment_method='微信支付',
         tracking_no='SF1234567890', shipping_company='顺丰速运',
         receiver_name='张先生', receiver_address='北京市朝阳区望京街道88号院3号楼501',
         remark=None),
    dict(order_no='ORDER20260820002', status='pending_payment', product_name='多功能空气炸锅 5L',
         quantity=1, total_amount=309.00, payment_method=None,
         tracking_no=None, shipping_company=None,
         receiver_name='张先生', receiver_address='北京市朝阳区望京街道88号院3号楼501',
         remark='满300减40 已优惠40元'),
    dict(order_no='ORDER20260825003', status='delivered', product_name='便携保温杯 500ml',
         quantity=2, total_amount=193.50, payment_method='支付宝',
         tracking_no='YT9876543210', shipping_company='圆通速递',
         receiver_name='张先生', receiver_address='北京市朝阳区望京街道88号院3号楼501',
         remark='第二件半价'),
    dict(order_no='ORDER20260810004', status='refunded', product_name='轻弹力运动鞋',
         quantity=1, total_amount=499.00, payment_method='微信支付',
         tracking_no='JD7788990011', shipping_company='京东物流',
         receiver_name='张先生', receiver_address='北京市朝阳区望京街道88号院3号楼501',
         remark='尺码不合适，已退款'),
]


async def seed_all(db: AsyncSession) -> None:
    """写入全部种子数据（幂等：已有数据则跳过）"""
    # 意图
    existing = (await db.execute(select(Intent).limit(1))).scalar_one_or_none()
    if not existing:
        for name, code, handler, desc, priority, samples in INTENTS:
            db.add(Intent(intent_name=name, intent_code=code, description=desc,
                          handler_type=handler, priority=priority, sample_utterances=samples))
        logger.info(f'已写入 {len(INTENTS)} 个意图')

    # 用户
    user_count = (await db.execute(select(User.id).limit(1))).scalar_one_or_none()
    if user_count is None:
        for u in DEMO_USERS:
            db.add(User(**u))
        await db.flush()
        logger.info('已写入演示用户')

    # 商品
    product_count = (await db.execute(select(Product.id).limit(1))).scalar_one_or_none()
    if product_count is None:
        for p in DEMO_PRODUCTS:
            db.add(Product(**p))
        logger.info(f'已写入 {len(DEMO_PRODUCTS)} 个演示商品')

    # 订单
    order_count = (await db.execute(select(Order.id).limit(1))).scalar_one_or_none()
    if order_count is None:
        demo_user = (await db.execute(select(User).where(User.username == 'demo_user'))).scalar_one()
        for o in DEMO_ORDERS:
            db.add(Order(user_id=demo_user.id, **o))
        logger.info(f'已写入 {len(DEMO_ORDERS)} 个演示订单')

    await db.commit()

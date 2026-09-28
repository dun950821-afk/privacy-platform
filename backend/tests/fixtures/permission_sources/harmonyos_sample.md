# 开放权限（用户授权）

此列表内所有权限均为用户授权（user_grant）的开放权限，面向所有应用开放。

## ohos.permission.ACCESS_BLUETOOTH

允许应用接入蓝牙并使用蓝牙功能。

包括扫描和发现外围蓝牙设备、与外围蓝牙设备配对和连接等操作。

**权限级别**：normal

**授权方式**：用户授权（user_grant）

**起始版本**：10

## ohos.permission.MEDIA_LOCATION

允许应用访问用户媒体文件中的地理位置信息。

**权限级别**：normal

**授权方式**：用户授权（user_grant）

**起始版本**：7

## ohos.permission.NOT_A_REAL_EXAMPLE_WITHOUT_FIELDS

这条没有结构化字段，应被解析器跳过而不是编造级别。

## ohos.permission.NO_LEVEL_OF_ITS_OWN

这条自己没有权限级别字段。

## 说明

**权限级别**：normal

上面那段是非权限小节。它的级别**不该被前一条借走**——正文只被下一个
`## ohos.permission.X` 收口的话，这段会被吞进前一条，而级别是 search 出来的，
前一条就会带着这里的级别入库。

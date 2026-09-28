/**
 * 合规画像用的中文词表。
 *
 * 与后端 `app/services/compliance_profile.py` 的 DATA_CATEGORY_CN 保持一致：后端返回
 * 的是机器可读的 data_category（device_information 等），中文名在前端兜底，避免后端
 * 国际化字段散落到每个接口里。**两边改一处要同时改另一处。**
 */
export const DATA_CATEGORY_CN: Record<string, string> = {
  device_information: '设备标识信息',
  installed_apps: '已安装应用列表',
  network_information: '网络信息（WiFi/基站）',
  location: '位置信息',
  contacts: '通讯录',
  camera: '摄像头',
  microphone: '麦克风',
  media: '音视频采集',
  sensor: '传感器数据',
  clipboard: '剪贴板',
  files: '外部存储文件',
  phone: '电话状态',
  sms: '短信',
  photos: '相册图片',
  calendar: '日历',
  account: '账号信息',
  biometric: '生物识别',
  advertising_identifier: '广告标识符',
  personal_information: '个人信息',
  unknown: '未知',
}

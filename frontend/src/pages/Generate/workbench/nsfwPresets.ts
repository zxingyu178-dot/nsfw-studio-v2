/**
 * NSFW 分级模板与标签词库（内置自本机 skill `nsfw-v2-pipeline`，v0.37.7 扩充）。
 *
 * 结构：
 * - 质量词 + 评级词由模型体系决定（MiaoMiao = 当前动漫工作流；WAI = 外部脚本）；
 * - 每个等级下有多套场景模板（variant），模板本身只描述画面标签；
 * - 标签库按「位次 / 动作 / 单人 / 口手足乳 / 体液 / 表情 / 服饰 / 镜头 / 场景 / 成年锚定」分类。
 *
 * 全部面向成年虚构角色；负向固定包含未成年压制词，任何套用都不得移除。
 */

export type NsfwModelSystem = 'miao' | 'wai'
export type NsfwLevel = 'L1' | 'L2' | 'L3'

/** 正面成年锚定：每张图必带。 */
export const NSFW_ADULT_ANCHOR = 'adult, mature female, 25 years old'

/** 负面未成年压制：不可移除。 */
export const NSFW_SAFETY_NEGATIVE = 'child, loli, toddler, young, aged down'

export const NSFW_MODEL_LABEL: Record<NsfwModelSystem, string> = {
  miao: 'MiaoMiao v14（当前动漫工作流）',
  wai: 'WAI v15（外部脚本体系）',
}

export const NSFW_QUALITY: Record<NsfwModelSystem, string> = {
  miao: 'score_9, score_8_up, score_7_up, source_anime',
  wai: 'masterpiece, best quality, amazing quality, very aesthetic, absurdres',
}

export const NSFW_NEGATIVE_BASE: Record<NsfwModelSystem, string> = {
  miao:
    'worst quality, low quality, score_1, score_2, score_3, bad hands, extra digits, ' +
    'blurry, watermark, child, loli, toddler, young, aged down',
  wai:
    'worst quality, low quality, bad anatomy, bad hands, extra digits, missing fingers, ' +
    'blurry, watermark, child, loli, toddler, young, aged down',
}

export const NSFW_RATING: Record<NsfwModelSystem, Record<NsfwLevel, string>> = {
  miao: {
    L1: 'rating_sensitive',
    L2: 'rating_questionable',
    L3: 'rating_explicit',
  },
  wai: {
    L1: 'sensitive',
    L2: 'sensitive, nsfw',
    L3: 'nsfw, explicit',
  },
}

export interface NsfwTemplateVariant {
  id: string
  label: string
  description: string
  /** 画面标签（不含质量词 / 评级词；成年锚定已内置）。 */
  tags: string
}

export interface NsfwLevelMeta {
  level: NsfwLevel
  label: string
  description: string
  variants: NsfwTemplateVariant[]
}

export const NSFW_LEVELS: NsfwLevelMeta[] = [
  {
    level: 'L1',
    label: 'L1 暗示级',
    description: '湿身、透视、汗水与遮胸姿态，擦边但不露。',
    variants: [
      {
        id: 'onsen-wet',
        label: '温泉湿身',
        description: '蒸汽、湿发、湿透衬衫与遮胸侧视。',
        tags:
          '1girl, adult, mature female, 25 years old, solo, wet shirt, see-through, wet hair, ' +
          'onsen, hot spring, steam, embarrassed, blush, covering breasts, medium breasts, ' +
          'long hair, side view',
      },
      {
        id: 'gym-sweat',
        label: '健身汗湿',
        description: '运动内衣、汗湿皮肤与健身房顶光。',
        tags:
          '1girl, adult, mature female, 25 years old, solo, sports bra, yoga pants, sweat, ' +
          'sweaty clothes, toned body, midriff, gym, fluorescent lights, from side, looking at viewer',
      },
      {
        id: 'pool-bikini',
        label: '泳池比基尼',
        description: '水珠、阳光与俯拍泳池边。',
        tags:
          '1girl, adult, mature female, 25 years old, solo, micro bikini, string bikini, ' +
          'wet body, water droplets, poolside, swimming pool, sunlight, from above, looking up',
      },
    ],
  },
  {
    level: 'L2',
    label: 'L2 擦边级',
    description: '内衣、丝袜、浴巾与半裸；无直接裸露。',
    variants: [
      {
        id: 'lace-bed',
        label: '黑蕾丝床躺',
        description: '蕾丝内衣、吊袜带与俯拍床面。',
        tags:
          '1girl, adult, mature female, 25 years old, solo, black lace lingerie, bra, panties, ' +
          'garter belt, thighhighs, cleavage, large breasts, seductive smile, lying on bed, ' +
          'on bed, bedroom, soft lighting, from above',
      },
      {
        id: 'office-tights',
        label: '办公室丝袜',
        description: '衬衫、包臀裙、黑丝与仰拍办公桌。',
        tags:
          '1girl, adult, mature female, 25 years old, solo, office lady, white blouse, ' +
          'black pencil skirt, black pantyhose, garter straps, desk, office, window light, ' +
          'sitting, crossed legs, from below',
      },
      {
        id: 'bath-towel',
        label: '浴室浴巾',
        description: '浴巾、湿发与镜面回望。',
        tags:
          '1girl, adult, mature female, 25 years old, solo, naked towel, wet hair, bare shoulders, ' +
          'bath, bathroom, steam, mirror, reflection, from behind, looking back',
      },
      {
        id: 'apron-kitchen',
        label: '裸围裙',
        description: '裸体围裙、侧乳与厨房暖光。',
        tags:
          '1girl, adult, mature female, 25 years old, solo, naked apron, sideboob, underboob, ' +
          'kitchen, cooking, from side, warm lighting, blush',
      },
    ],
  },
  {
    level: 'L3',
    label: 'L3 explicit',
    description: '完整成人场景；双模型解剖已在 R5 实测。',
    variants: [
      {
        id: 'missionary-bed',
        label: '传教士 · 床',
        description: '床单、汗珠与亲密特写。',
        tags:
          '1girl, 1boy, adult, mature female, 25 years old, hetero, sex, vaginal, missionary, ' +
          'lying, on bed, bed sheet, nude, nipples, spread legs, blush, sweating, moaning, ' +
          'bedroom, intimate',
      },
      {
        id: 'doggy-sofa',
        label: '后入 · 沙发',
        description: '四肢跪撑、背后视角与客厅。',
        tags:
          '1girl, 1boy, adult, mature female, 25 years old, hetero, sex, vaginal, doggy style, ' +
          'all fours, on sofa, living room, from behind, ass, sweat, moaning, motion lines',
      },
      {
        id: 'cowgirl-mirror',
        label: '骑乘 · 镜前',
        description: '女上位、镜面反射与侧拍。',
        tags:
          '1girl, 1boy, adult, mature female, 25 years old, hetero, sex, cowgirl position, ' +
          'girl on top, nude, nipples, bouncing breasts, mirror, reflection, bedroom, from side, blush',
      },
      {
        id: 'blowjob-kneel',
        label: '口交 · 跪姿',
        description: '跪姿仰视、口内与 POV。',
        tags:
          '1girl, 1boy, adult, mature female, 25 years old, hetero, oral, blowjob, kneeling, ' +
          'looking up, cum in mouth, saliva, bedroom, pov',
      },
      {
        id: 'paizuri-bed',
        label: '乳交 · 床',
        description: '乳沟、俯拍与射胸。',
        tags:
          '1girl, 1boy, adult, mature female, 25 years old, hetero, paizuri, large breasts, ' +
          'cleavage, cum on breasts, on bed, bedroom, from above, blush',
      },
      {
        id: 'wall-standing',
        label: '站姿 · 靠墙',
        description: '按墙、抬腿与办公室侧拍。',
        tags:
          '1girl, 1boy, adult, mature female, 25 years old, hetero, sex, standing sex, wall, ' +
          'pinned against wall, leg lift, skirt lift, office, from side, intense',
      },
    ],
  },
]

/** 质量词 + 评级词 + 指定场景模板；variantId 缺省取该等级第一套。 */
export function buildLevelPrompt(
  level: NsfwLevel,
  model: NsfwModelSystem,
  variantId?: string,
): string {
  const meta = NSFW_LEVELS.find((item) => item.level === level) ?? NSFW_LEVELS[0]
  const variant = meta.variants.find((item) => item.id === variantId) ?? meta.variants[0]
  return [NSFW_QUALITY[model], NSFW_RATING[model][level], variant.tags].join(', ')
}

/** 负向固定基线（含未成年压制词）。 */
export function buildLevelNegative(model: NsfwModelSystem): string {
  return NSFW_NEGATIVE_BASE[model]
}

export interface NsfwTag {
  tag: string
  label: string
  /** 悬停简介（画师 / 画面风格 / 复杂套装）。 */
  note?: string
  /** 点击后实际提交的完整标签串；用于「简称 + 详细展开」的套装。 */
  expand?: string
  /** WAI / Danbooru 体系下的写法（画师 tag 去掉 @ 前缀）。 */
  waiTag?: string
}

export interface NsfwTagGroup {
  id: string
  label: string
  hint?: string
  tags: NsfwTag[]
}

export const NSFW_TAG_GROUPS: NsfwTagGroup[] = [
  {
    id: 'position',
    label: '位次',
    hint: 'L3 主标签，一次只用 1 个',
    tags: [
      { tag: 'missionary', label: '传教士位' },
      { tag: 'doggy style', label: '后入位' },
      { tag: 'sex from behind', label: '背后位' },
      { tag: 'cowgirl position', label: '女骑乘' },
      { tag: 'reverse cowgirl', label: '反向骑乘' },
      { tag: 'standing sex', label: '站立位' },
      { tag: 'girl on top', label: '女上位' },
      { tag: 'face sitting', label: '坐脸' },
      { tag: 'prone bone', label: '俯卧后入' },
      { tag: 'pile driver position', label: '钻头位' },
      { tag: 'mating press', label: '压腿位' },
      { tag: 'wall sex', label: '靠墙位' },
      { tag: 'pinned against wall', label: '按在墙上' },
      { tag: 'seated lap sex', label: '膝上位' },
      { tag: 'window sex', label: '窗边位' },
      { tag: 'leg locking', label: '双腿锁腰' },
      { tag: 'intercrural', label: '腿间摩擦' },
      { tag: 'double penetration', label: '双插' },
      { tag: 'clothed sex', label: '着装性爱' },
      { tag: 'squatting cowgirl', label: '蹲骑' },
      { tag: 'spooning', label: '侧卧位' },
      { tag: 'suspended congress', label: '抱起位' },
    ],
  },
  {
    id: 'motion',
    label: '动作与互动',
    hint: '配 2–3 个',
    tags: [
      { tag: 'thrusting', label: '抽动' },
      { tag: 'deep penetration', label: '深插' },
      { tag: 'grinding', label: '磨蹭' },
      { tag: 'hip movement', label: '摆胯' },
      { tag: 'pinned down', label: '被按住' },
      { tag: 'wrist grab', label: '扣腕' },
      { tag: 'hair pull', label: '抓头发' },
      { tag: 'leg lift', label: '抬腿' },
      { tag: 'arms up', label: '双手举高' },
      { tag: 'sweating', label: '汗珠' },
      { tag: 'trembling', label: '颤抖' },
      { tag: 'kissing', label: '接吻' },
      { tag: 'breast grab', label: '揉胸' },
      { tag: 'spanking', label: '拍打' },
      { tag: 'undressing partner', label: '脱对方衣服' },
      { tag: 'looking at partner', label: '看向对方' },
    ],
  },
  {
    id: 'solo',
    label: '单人',
    hint: '自慰 / 玩具 / 姿态',
    tags: [
      { tag: 'masturbation', label: '自慰' },
      { tag: 'fingering', label: '手指' },
      { tag: 'dildo', label: '假阳具' },
      { tag: 'vibrator', label: '震动棒' },
      { tag: 'sex toy', label: '成人玩具' },
      { tag: 'nipple stimulation', label: '刺激乳头' },
      { tag: 'all fours', label: '四肢跪撑' },
      { tag: 'bent over', label: '弯腰' },
      { tag: 'spread legs', label: '张腿' },
      { tag: 'squatting', label: '蹲姿' },
      { tag: 'kneeling', label: '跪姿' },
      { tag: 'on back', label: '仰躺' },
      { tag: 'lying on stomach', label: '趴卧' },
      { tag: 'panties pulled aside', label: '内裤拨开' },
      { tag: 'panties around ankle', label: '内裤褪至脚踝' },
      { tag: 'skirt around waist', label: '裙卷到腰' },
      { tag: 'anal beads', label: '后庭珠' },
      { tag: 'double-sided dildo', label: '双头假阳' },
      { tag: 'dildo riding', label: '坐假阳' },
      { tag: 'suction cup dildo', label: '吸盘假阳' },
      { tag: 'onahole', label: '飞机杯' },
      { tag: 'magic wand', label: '魔棒' },
    ],
  },
  {
    id: 'oral',
    label: '口 / 手 / 足 / 乳',
    tags: [
      { tag: 'blowjob', label: '口交' },
      { tag: 'deepthroat', label: '深喉' },
      { tag: 'handjob', label: '手交' },
      { tag: 'footjob', label: '足交' },
      { tag: 'paizuri', label: '乳交' },
      { tag: 'cunnilingus', label: '舔阴' },
      { tag: 'oral', label: '口侍' },
      { tag: 'licking', label: '舔舐' },
      { tag: 'saliva', label: '唾液' },
      { tag: 'tongue out', label: '伸舌' },
    ],
  },
  {
    id: 'fluid',
    label: '体液 / 高潮',
    tags: [
      { tag: 'ejaculation', label: '射精' },
      { tag: 'facial', label: '面部' },
      { tag: 'ejaculation in mouth', label: '口内' },
      { tag: 'ejaculation on breasts', label: '射胸' },
      { tag: 'cum on body', label: '身上残留' },
      { tag: 'creampie', label: '中出' },
      { tag: 'dripping', label: '滴落' },
      { tag: 'squirt', label: '潮吹' },
      { tag: 'wet', label: '湿润' },
      { tag: 'afterglow', label: '事后余韵' },
      { tag: 'after sex', label: '事后' },
      { tag: 'used condom', label: '安全套' },
    ],
  },
  {
    id: 'reaction',
    label: '表情 / 反应',
    tags: [
      { tag: 'moaning', label: '呻吟' },
      { tag: 'expression of pleasure', label: '愉悦表情' },
      { tag: 'ahegao', label: '阿黑颜' },
      { tag: 'heart-shaped pupils', label: '心形瞳' },
      { tag: 'orgasm', label: '高潮' },
      { tag: 'breathing heavily', label: '急促呼吸' },
      { tag: 'satisfied smile', label: '满足微笑' },
      { tag: 'shy', label: '害羞' },
      { tag: 'embarrassed', label: '难为情' },
      { tag: 'blush', label: '脸红' },
      { tag: 'tears', label: '泪光' },
      { tag: 'rolling eyes', label: '翻白眼' },
      { tag: 'drooling', label: '流涎' },
      { tag: 'biting lip', label: '咬唇' },
    ],
  },
  {
    id: 'outfit',
    label: '日常服饰',
    hint: 'L1–L3 均可',
    tags: [
      { tag: 'white dress', label: '白色连衣裙' },
      { tag: 'red dress', label: '红色连衣裙' },
      {
        tag: 'black evening gown',
        label: '黑色晚礼服',
        expand:
          'black evening gown, high slit, off-shoulder, satin, elegant, long gloves, pearl necklace, ' +
          'upswept hair, chandelier light, ballroom',
        note: '整套晚宴造型：缎面、开衩、长手套与舞厅光。',
      },
      { tag: 'knit sweater', label: '针织毛衣' },
      { tag: 'off-shoulder sweater', label: '露肩毛衣' },
      { tag: 'denim shorts', label: '牛仔短裤' },
      { tag: 'hot pants', label: '热裤' },
      { tag: 'pleated skirt', label: '百褶裙' },
      { tag: 'pencil skirt', label: '包臀裙' },
      {
        tag: 'trench coat',
        label: '风衣',
        expand: 'beige trench coat, belt, open coat, high collar, boots',
        note: '风衣敞开穿法，适合街头与秋日场景。',
      },
      { tag: 'leather jacket', label: '皮夹克' },
      { tag: 'jumpsuit', label: '连体裤' },
      { tag: 'tracksuit', label: '运动套装' },
      {
        tag: 'yoga set',
        label: '瑜伽套装',
        expand: 'sports bra, yoga pants, toned body, midriff, sneakers',
        note: '运动内衣 + 瑜伽裤，适合健身与居家场景。',
      },
      {
        tag: 'silk pajamas',
        label: '丝绸睡衣',
        expand: 'silk pajamas, buttoned shirt, loose shorts, bare shoulders, morning light',
        note: '丝质睡衣套装，偏居家暧昧。',
      },
      { tag: 'nightgown', label: '睡裙' },
      {
        tag: 'yukata',
        label: '浴衣',
        expand: 'yukata, obi, off shoulder, wooden clogs, summer festival, lantern light',
        note: '夏日祭浴衣：露肩、腰带与灯笼光。',
      },
      { tag: 'kimono', label: '和服' },
      {
        tag: 'qipao',
        label: '旗袍',
        expand: 'qipao, china dress, high collar, side slit, frog buttons, floral pattern, thighhighs',
        note: '高领、盘扣与开衩，适合中式场景。',
      },
      {
        tag: 'hanfu',
        label: '汉服',
        expand: 'hanfu, wide sleeves, flowing ribbons, embroidery, hair ornament, ancient style',
        note: '宽袖、飘带与刺绣，古风场景。',
      },
      {
        tag: 'wedding dress',
        label: '婚纱',
        expand: 'wedding dress, veil, white lace, strapless, bouquet, wedding chapel, soft light',
        note: '婚纱套装：头纱、蕾丝、捧花与教堂光。',
      },
      {
        tag: 'lolita fashion',
        label: '洛丽塔',
        expand: 'lolita fashion, frilled dress, petticoat, bonnet, lace trim, ribbon, thighhighs',
        note: '荷叶边、裙撑、发帽与长袜的完整 Lo 装。',
      },
      {
        tag: 'gothic lolita',
        label: '哥特洛丽塔',
        expand: 'gothic lolita, black frilled dress, corset, lace trim, bonnet, bat motif, thighhighs',
        note: '黑系 Lo 装，配束腰与蝙蝠元素。',
      },
      { tag: 'bikini', label: '比基尼' },
      { tag: 'one-piece swimsuit', label: '连体泳衣' },
      { tag: 'apron', label: '围裙' },
      { tag: 'naked apron', label: '裸体围裙' },
      {
        tag: 'wet shirt',
        label: '湿衬衫',
        expand: 'wet shirt, see-through, clinging to body, wet hair, water droplets, white shirt',
        note: '湿透白衬衫贴身的透视效果。',
      },
      {
        tag: 'torn clothes',
        label: '破损衣物',
        expand: 'torn clothes, torn pantyhose, ripped shirt, battle damage, dirt, scratches',
        note: '战损 / 撕扯后的衣物，配脏污与划痕。',
      },
    ],
  },
  {
    id: 'uniform',
    label: '制服 / 角色扮演',
    hint: '简称背后是完整套装',
    tags: [
      {
        tag: 'green school uniform',
        label: '华丽绿色 JK',
        expand:
          'green school uniform, green blazer, gold trim, white blouse, red ribbon tie, ' +
          'green pleated skirt, black thighhighs, brown loafers, school bag, hair bow, ' +
          'classroom, afternoon light',
        note: '绿色西装外套 + 金边 + 红领结 + 绿百褶裙 + 黑过膝袜，共 12 个标签。',
      },
      {
        tag: 'navy school uniform',
        label: '经典藏蓝 JK',
        expand:
          'navy sailor uniform, white shirt, red ribbon, navy pleated skirt, knee socks, ' +
          'loafers, school bag, classroom, window light',
        note: '藏蓝水手服 + 白衬衫 + 红领结 + 及膝袜，经典校园组合。',
      },
      { tag: 'sailor uniform', label: '水手服' },
      {
        tag: 'maid outfit',
        label: '女仆装',
        expand:
          'maid outfit, black and white maid dress, frilled apron, maid headdress, ' +
          'wrist cuffs, white thighhighs, black shoes',
        note: '黑白女仆裙 + 荷叶围裙 + 头饰 + 腕套，共 7 个标签。',
      },
      {
        tag: 'cat ear maid outfit',
        label: '猫耳女仆',
        expand:
          'cat ear maid outfit, black and white maid dress, frilled apron, cat ears, ' +
          'cat paw gloves, yellow bells on chest and waist, small black animal tail, ' +
          'thighhighs, kitchen counter, morning light',
        note: '猫耳 + 猫爪手套 + 铃铛 + 尾巴的完整猫女仆套装（来自本机采集样本）。',
      },
      {
        tag: 'nurse outfit',
        label: '护士服',
        expand: 'nurse uniform, white dress, nurse cap, red cross, white thighhighs, hospital room',
        note: '白色护士裙 + 护士帽 + 红十字 + 白丝。',
      },
      {
        tag: 'office lady',
        label: 'OL 套装',
        expand:
          'office lady, white blouse, black pencil skirt, black pantyhose, garter straps, ' +
          'high heels, desk, office, window light',
        note: '白衬衫 + 包臀裙 + 黑丝 + 高跟鞋，共 9 个标签。',
      },
      { tag: 'police uniform', label: '女警服' },
      { tag: 'military uniform', label: '军装' },
      {
        tag: 'flight attendant',
        label: '空姐服',
        expand: 'flight attendant, uniform, neckerchief, pencil skirt, pantyhose, heels, airplane cabin',
        note: '制服 + 丝巾 + 包臀裙 + 丝袜，机舱场景。',
      },
      {
        tag: 'miko',
        label: '巫女服',
        expand: 'miko, red hakama, white haori, wide sleeves, shrine, torii, paper lantern',
        note: '白衣红袴 + 神社鸟居场景。',
      },
      { tag: 'nun habit', label: '修女服' },
      {
        tag: 'bunny girl',
        label: '兔女郎',
        expand:
          'bunny girl, leotard, bunny ears, fishnet pantyhose, wrist cuffs, collar bowtie, high heels',
        note: '连体衣 + 兔耳 + 渔网袜 + 腕套 + 领结。',
      },
      {
        tag: 'cheerleader',
        label: '啦啦队',
        expand: 'cheerleader, crop top, pleated mini skirt, pom poms, knee socks, stadium',
        note: '露腰短上衣 + 迷你百褶裙 + 彩球。',
      },
      {
        tag: 'gym uniform',
        label: '体操服',
        expand: 'gym uniform, buruma, white shirt, red bloomers, thighhighs, locker room',
        note: '白上衣 + 红运动短裤（buruma），更衣室场景。',
      },
      {
        tag: 'school swimsuit',
        label: '校园泳装',
        expand: 'school swimsuit, sukumizu, name tag, one-piece swimsuit, wet skin, poolside',
        note: '死库水 + 名牌 + 泳池边。',
      },
      {
        tag: 'cyberpunk outfit',
        label: '赛博朋克装',
        expand: 'cyberpunk outfit, neon trim, techwear, straps, glowing accents, city lights',
        note: '机能风 + 霓虹发光条 + 城市夜景。',
      },
      { tag: 'armor', label: '骑士铠甲' },
      { tag: 'ninja outfit', label: '忍者装' },
      { tag: 'pirate outfit', label: '海盗装' },
      {
        tag: 'vampire dress',
        label: '吸血鬼礼服',
        expand: 'vampire dress, gothic gown, high collar, cape, bat wings, candelabra, castle',
        note: '高领哥特礼服 + 披风 + 蝙蝠翼。',
      },
      {
        tag: 'succubus outfit',
        label: '魅魔装',
        expand: 'succubus, horns, demon tail, bat wings, leather harness, thighhighs, glowing eyes',
        note: '角 + 尾巴 + 蝠翼 + 皮质束带。',
      },
      {
        tag: 'angel outfit',
        label: '天使装',
        expand: 'angel, halo, white wings, white dress, feathered wings, holy light',
        note: '光环 + 白翼 + 白裙 + 圣光。',
      },
      { tag: 'gothic dress', label: '哥特裙' },
    ],
  },
  {
    id: 'lingerie',
    label: '内衣 / 丝袜',
    hint: 'L2 / L3',
    tags: [
      {
        tag: 'black lace lingerie',
        label: '黑蕾丝内衣',
        expand: 'black lace lingerie, bra, panties, garter belt, thighhighs, cleavage, lace trim',
        note: '黑蕾丝三件套 + 吊袜带 + 长袜。',
      },
      {
        tag: 'white lingerie',
        label: '白内衣',
        expand: 'white lingerie, lace bra, lace panties, garter belt, white thighhighs',
        note: '白色蕾丝套装，配白丝与吊袜带。',
      },
      { tag: 'bralette', label: '无钢圈内衣' },
      { tag: 'sports bra', label: '运动内衣' },
      { tag: 'lace panties', label: '蕾丝内裤' },
      { tag: 'lace thong', label: '蕾丝丁字裤' },
      { tag: 'garter belt', label: '吊袜带' },
      {
        tag: 'black pantyhose',
        label: '黑丝',
        expand: 'black pantyhose, sheer pantyhose, glossy, high heels',
        note: '半透黑丝 + 高跟，偏 OL / 晚宴。',
      },
      { tag: 'white pantyhose', label: '白丝' },
      { tag: 'fishnet thighhighs', label: '渔网袜' },
      { tag: 'thighhighs', label: '过膝袜' },
      { tag: 'striped thighhighs', label: '条纹过膝袜' },
      { tag: 'lace stockings', label: '蕾丝长袜' },
      { tag: 'fishnet', label: '网袜' },
      {
        tag: 'sheer nightgown',
        label: '半透明睡裙',
        expand: 'sheer nightgown, see-through, lace trim, bare shoulders, moonlight, bedroom',
        note: '半透材质 + 蕾丝边 + 月光卧室。',
      },
      { tag: 'babydoll', label: '娃娃装' },
      { tag: 'bodysuit', label: '紧身连体衣' },
      { tag: 'corset', label: '束腰' },
      { tag: 'no bra', label: '无胸罩' },
      { tag: 'no panties', label: '无内裤' },
      { tag: 'panties pulled aside', label: '内裤拨开' },
      { tag: 'wet lingerie', label: '湿透内衣' },
    ],
  },
  {
    id: 'accessory',
    label: '装饰品',
    hint: '可与其他服饰叠加',
    tags: [
      { tag: 'hair bow', label: '发间蝴蝶结' },
      { tag: 'hairband', label: '发带' },
      { tag: 'hairclip', label: '发夹' },
      { tag: 'hair stick', label: '发簪' },
      { tag: 'flower crown', label: '花冠' },
      { tag: 'maid headdress', label: '女仆头饰' },
      { tag: 'beret', label: '贝雷帽' },
      { tag: 'cat ears', label: '猫耳' },
      { tag: 'fox ears', label: '狐狸耳' },
      { tag: 'bunny ears', label: '兔耳' },
      { tag: 'horns', label: '角' },
      { tag: 'halo', label: '光环' },
      { tag: 'earrings', label: '耳环' },
      { tag: 'stud earrings', label: '耳钉' },
      { tag: 'necklace', label: '项链' },
      { tag: 'pearl necklace', label: '珍珠项链' },
      { tag: 'choker', label: '颈圈' },
      { tag: 'collarbone chain', label: '锁骨链' },
      { tag: 'bracelet', label: '手链' },
      { tag: 'anklet', label: '脚链' },
      { tag: 'ring', label: '戒指' },
      { tag: 'body chain', label: '身体链' },
      { tag: 'nipple rings', label: '乳环' },
      { tag: 'navel piercing', label: '肚脐钉' },
      { tag: 'tongue piercing', label: '舌钉' },
      { tag: 'tattoo', label: '纹身' },
      { tag: 'womb tattoo', label: '淫纹' },
      { tag: 'back tattoo', label: '背部纹身' },
      { tag: 'glasses', label: '眼镜' },
      { tag: 'round eyewear', label: '圆框眼镜' },
      { tag: 'sunglasses', label: '墨镜' },
      { tag: 'eyepatch', label: '眼罩' },
      { tag: 'veil', label: '面纱' },
      { tag: 'fox mask', label: '狐面' },
      { tag: 'gloves', label: '手套' },
      { tag: 'lace gloves', label: '蕾丝手套' },
      { tag: 'elbow gloves', label: '长手套' },
      { tag: 'cat paw gloves', label: '猫爪手套' },
      { tag: 'arm warmers', label: '袖套' },
      { tag: 'thigh ring', label: '腿环' },
      { tag: 'belt', label: '腰带' },
      { tag: 'harness', label: '束带' },
      { tag: 'collar', label: '项圈' },
      { tag: 'bell', label: '铃铛' },
      { tag: 'tail', label: '尾巴' },
      { tag: 'wings', label: '翅膀' },
      { tag: 'cape', label: '披风' },
      { tag: 'lace trim', label: '蕾丝边' },
      { tag: 'ribbon', label: '丝带' },
    ],
  },
  {
    id: 'framing',
    label: '镜头 / 构图',
    tags: [
      { tag: 'pov', label: '第一人称' },
      { tag: 'from above', label: '俯拍' },
      { tag: 'from below', label: '仰拍' },
      { tag: 'from behind', label: '背后视角' },
      { tag: 'from side', label: '侧拍' },
      { tag: 'close-up', label: '特写' },
      { tag: 'upper body', label: '半身' },
      { tag: 'full body', label: '全身' },
      { tag: 'cowboy shot', label: '七分身' },
      { tag: 'dutch angle', label: '倾斜构图' },
      { tag: 'depth of field', label: '景深' },
      { tag: 'motion lines', label: '动态线' },
      { tag: 'looking at viewer', label: '看向镜头' },
      { tag: 'looking back', label: '回望' },
      { tag: 'spread legs', label: '张腿构图' },
      { tag: 'legs up', label: '举腿' },
    ],
  },
  {
    id: 'scene',
    label: '场景 / 环境',
    tags: [
      { tag: 'bedroom', label: '卧室' },
      { tag: 'on bed', label: '床上' },
      { tag: 'bed sheet', label: '床单' },
      { tag: 'love hotel', label: '情侣酒店' },
      { tag: 'living room', label: '客厅' },
      { tag: 'on sofa', label: '沙发上' },
      { tag: 'kitchen', label: '厨房' },
      { tag: 'office', label: '办公室' },
      { tag: 'desk', label: '办公桌' },
      { tag: 'bathroom', label: '浴室' },
      { tag: 'bath', label: '浴缸' },
      { tag: 'shower', label: '淋浴' },
      { tag: 'steam', label: '蒸汽' },
      { tag: 'onsen', label: '温泉' },
      { tag: 'hot spring', label: '温泉池' },
      { tag: 'swimming pool', label: '泳池' },
      { tag: 'poolside', label: '池边' },
      { tag: 'beach', label: '沙滩' },
      { tag: 'gym', label: '健身房' },
      { tag: 'mirror', label: '镜子' },
      { tag: 'reflection', label: '镜面反射' },
      { tag: 'soft lighting', label: '柔光' },
      { tag: 'window light', label: '窗光' },
      { tag: 'candlelight', label: '烛光' },
    ],
  },
  {
    id: 'artist',
    label: '画师风格',
    hint: '悬停看简介；MiaoMiao 用 @，WAI 自动去前缀',
    tags: [
      { tag: '@wlop', waiTag: 'wlop', label: 'wlop', note: '厚涂质感、强逆光与飘散发丝，偏半写实奇幻。' },
      { tag: '@rella', waiTag: 'rella', label: 'rella', note: '粉彩水彩、柔和边缘，梦幻少女氛围。' },
      { tag: '@ciloranko', waiTag: 'ciloranko', label: 'ciloranko', note: '高饱和配色与强透视，画面张力大。' },
      { tag: '@morikura en', waiTag: 'morikura en', label: 'morikura en', note: '清爽线条与轻小说插画感，适合日常场景。' },
      { tag: '@hi ye', waiTag: 'hi ye', label: 'hi ye', note: '电影感构图与冷暖对比，氛围克制。' },
      { tag: '@sw33t', waiTag: 'sw33t', label: 'sw33t', note: '柔和厚涂、粉嫩肤色，偏甜系。' },
      { tag: '@z3zz4', waiTag: 'z3zz4', label: 'z3zz4', note: '细腻赛璐璐与透明高光，二次元感强。' },
      { tag: '@ratatatat74', waiTag: 'ratatatat74', label: 'ratatatat74', note: '高对比硬光、厚重阴影，偏成熟写实。' },
      { tag: '@quasarcake', waiTag: 'quasarcake', label: 'quasarcake', note: '明亮糖果色与圆润造型，偏可爱。' },
      { tag: '@shiratama', waiTag: 'shiratama', label: 'shiratama', note: '通透赛璐璐、轻快线条，适合清爽场景。' },
      { tag: '@shinjiro', waiTag: 'shinjiro', label: 'shinjiro', note: '强光影与服装褶皱细节，画面完成度高。' },
      { tag: '@cogecha', waiTag: 'cogecha', label: 'cogecha', note: '低饱和复古色调，胶片氛围。' },
      { tag: '@yomu', waiTag: 'yomu', label: 'yomu', note: '柔和笔触与空气感，偏文艺。' },
      { tag: '@eruu', waiTag: 'eruu', label: 'eruu', note: '鲜亮色彩与细密发丝，偏华丽。' },
      { tag: '@hiten', waiTag: 'hiten', label: 'hiten', note: '细腻氛围光与柔和肤色，偏唯美。' },
      { tag: '@lpip', waiTag: 'lpip', label: 'lpip', note: '干净平涂与强轮廓线，漫画感。' },
      { tag: '@ponkan8', waiTag: 'ponkan8', label: 'ponkan8', note: '轻小说封面式构图，人物突出。' },
      { tag: '@sichinotuki', waiTag: 'sichinotuki', label: 'sichinotuki', note: '冷色调与锐利线条，偏酷感。' },
      { tag: '@ebora', waiTag: 'ebora', label: 'ebora', note: '浓郁色彩与装饰性细节，偏奇幻。' },
      { tag: '@kantoku', waiTag: 'kantoku', label: 'kantoku', note: '柔和渐变与透明感，少女氛围。' },
      { tag: '@mamerakkkkko', waiTag: 'mamerakkkkko', label: 'mamerakkkkko', note: '软萌圆润线条，偏治愈。' },
      { tag: '@anmi', waiTag: 'anmi', label: 'anmi', note: '清透高光与明亮配色，插画感强。' },
      { tag: '@riichu', waiTag: 'riichu', label: 'riichu', note: '干净赛璐璐与活泼表情，适合角色立绘。' },
    ],
  },
  {
    id: 'style',
    label: '画面风格',
    hint: '选 1–2 个，避免互相冲突',
    tags: [
      { tag: 'soft cel shading', label: '柔和赛璐璐', note: '明暗分界柔和，适合日常与恋爱场景。' },
      { tag: 'clean sharp line art', label: '锐利干净线稿', note: '线条清晰、边缘利落，偏插画与立绘。' },
      { tag: 'soft watercolor', label: '柔和水彩', note: '水彩晕染与留白，适合清新、梦幻题材。' },
      { tag: 'pastel colors', label: '粉彩色调', note: '低对比、高明度，甜系与治愈感。' },
      { tag: 'impasto', label: '厚涂', note: '笔触厚重、颜料堆叠，偏油画质感。' },
      { tag: 'painterly', label: '绘画质感', note: '弱化线稿、强调笔触与色块。' },
      { tag: 'cinematic lighting', label: '电影光影', note: '强方向光与明暗对比，画面有叙事感。' },
      { tag: 'high saturation', label: '高饱和', note: '色彩浓烈，适合赛博、魔法与强视觉冲击。' },
      { tag: 'muted warm tone', label: '低饱和暖调', note: '灰调暖色，复古与胶片氛围。' },
      { tag: 'retro anime', label: '复古动画', note: '模拟 80–90 年代赛璐璐动画质感。' },
      { tag: '90s anime', label: '90 年代动画', note: '粗线条、低色数与经典动画肤色。' },
      { tag: 'official art', label: '官方画风', note: '接近游戏 / 动画官方立绘的完成度。' },
      { tag: 'concept art', label: '概念设定', note: '强调设计感与场景气氛，适合大场景。' },
      { tag: 'illustration', label: '插画', note: '通用插画质感，兼容性最好。' },
      { tag: '3d render', label: '3D 渲染', note: '立体体积感与真实材质，偏离二次元线稿。' },
      { tag: 'pixel art', label: '像素风', note: '低分辨率像素块，复古游戏感。' },
      { tag: 'monochrome', label: '黑白', note: '单色画面，适合氛围与构图练习。' },
      { tag: 'lineart', label: '线稿', note: '仅线稿或轻上色，适合设定图。' },
      { tag: 'oil painting', label: '油画', note: '古典油画笔触与光泽，偏写实。' },
      { tag: 'ukiyo-e', label: '浮世绘', note: '日式木版画平涂与装饰性线条。' },
      { tag: 'cyberpunk', label: '赛博朋克', note: '霓虹、雨夜与高科技低生活质感。' },
      { tag: 'vaporwave', label: '蒸汽波', note: '粉紫渐变、网格与复古电子感。' },
      { tag: 'steampunk', label: '蒸汽朋克', note: '黄铜机械、齿轮与维多利亚服饰。' },
      { tag: 'gothic', label: '哥特', note: '暗色、尖顶与繁复装饰，偏阴郁。' },
      { tag: 'film grain', label: '胶片颗粒', note: '增加噪点与复古摄影质感。' },
      { tag: 'backlighting', label: '逆光', note: '光源在人物背后，强调轮廓与氛围。' },
      { tag: 'rim lighting', label: '轮廓光', note: '边缘高光勾出人物，暗背景更突出。' },
      { tag: 'volumetric lighting', label: '体积光', note: '可见光束，适合窗光、舞台与森林。' },
      { tag: 'glow', label: '发光', note: '高光与魔法光效，偏梦幻。' },
      { tag: 'detailed', label: '细节丰富', note: '增加服饰、发丝与环境细节密度。' },
      { tag: 'flat color', label: '平涂', note: '少渐变、色块明确，偏漫画与海报。' },
      { tag: 'sketch', label: '素描', note: '铅笔线条与排线阴影，偏手稿感。' },
      { tag: 'comic style', label: '美漫风', note: '粗轮廓、强阴影与网点，偏欧美漫画。' },
    ],
  },
  {
    id: 'anchor',
    label: '成年锚定',
    hint: '每张必带',
    tags: [
      { tag: 'adult', label: '成年' },
      { tag: 'mature female', label: '成熟女性' },
      { tag: '25 years old', label: '25 岁' },
      { tag: '1girl', label: '单人女性' },
    ],
  },
]

/** 点击后实际写入 Prompt 的文本：WAI 画师去 @；复杂套装展开完整标签串。 */
export function tagPayload(item: NsfwTag, model: NsfwModelSystem): string {
  if (model === 'wai' && item.waiTag) return item.waiTag
  return item.expand ?? item.tag
}

/** 详情等级 1–3：按实际提交的标签数量着色，越详细背景越深。 */
export function tagDetailLevel(item: NsfwTag): 1 | 2 | 3 {
  const count = (item.expand ?? item.tag).split(',').filter((part) => part.trim()).length
  if (count >= 8) return 3
  if (count >= 4) return 2
  return 1
}

/** 追加标签：去重、用逗号规范分隔。 */
export function appendPromptTag(current: string, tag: string): string {
  const parts = current
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean)
  if (parts.includes(tag)) return current
  return [...parts, tag].join(', ')
}

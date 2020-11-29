-- ----------------------------
-- Table structure for oj_checkpoint
-- ----------------------------
DROP TABLE IF EXISTS `oj_checkpoint`;
CREATE TABLE `oj_checkpoint` (
  `c_id` bigint(20) unsigned NOT NULL COMMENT '主键, 检查点id, 由雪花算法生成',
  `c_gmt_create` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `c_gmt_modified` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '修改时间',
  `c_features` varchar(128) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '特性字段',
  `c_input_preview` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT '输入文件概况, 64 字节',
  `c_output_preview` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT '输出文件概况, 64 字节',
  `c_input_size` int(11) unsigned NOT NULL COMMENT '输入文件大小, 单位: B',
  `c_output_size` int(11) unsigned NOT NULL COMMENT '输出文件大小, 单位: B',
  `c_input_file_name` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `c_output_file_name` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `c_input_file_id` bigint(20) unsigned NOT NULL COMMENT '输入文件的文件系统id',
  `c_output_file_id` bigint(20) unsigned NOT NULL COMMENT '输出文件的文件系统id',
  PRIMARY KEY (`c_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='检查点表';

-- ----------------------------
-- Records of oj_checkpoint
-- ----------------------------

-- ----------------------------
-- Table structure for oj_contest
-- ----------------------------
DROP TABLE IF EXISTS `oj_contest`;
CREATE TABLE `oj_contest` (
  `ct_id` bigint(20) unsigned NOT NULL AUTO_INCREMENT COMMENT '主键',
  `ct_gmt_create` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `ct_gmt_modified` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '修改时间',
  `ct_features` varchar(3072) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT '特性字段',
  `ct_is_deleted` tinyint(4) unsigned NOT NULL DEFAULT '0' COMMENT '是否删除, 0.否, 1.是',
  `ct_is_public` tinyint(4) unsigned NOT NULL DEFAULT '0' COMMENT '比赛公开, 0否, 1是',
  `ct_version` int(10) unsigned NOT NULL DEFAULT '0' COMMENT '乐观锁字段',
  `ct_title` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '比赛标题',
  `u_id` bigint(20) unsigned NOT NULL COMMENT '创建者id',
  `ct_gmt_start` datetime NOT NULL COMMENT '比赛开始时间',
  `ct_gmt_end` datetime NOT NULL COMMENT '比赛结束时间',
  `ct_password` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT '参加密码',
  `ct_source` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT '比赛来源',
  `ct_participant_num` mediumint(9) unsigned NOT NULL DEFAULT '0' COMMENT '参加人数',
  `ct_markdown_description` text COLLATE utf8mb4_unicode_ci COMMENT '比赛描述',
  `ct_problems` text COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '比赛题目设置, 包含(p_id,pd_id,title,score)',
  `ct_participants` blob COMMENT '参加者id集合, 最多支持8k个人参加比赛',
  `ct_unofficial_participants` blob COMMENT '挂星参加者id集合, 是参赛者的子集, 最多支持8k个人参加比赛',
  PRIMARY KEY (`ct_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='比赛表';

-- ----------------------------
-- Records of oj_contest
-- ----------------------------

-- ----------------------------
-- Table structure for oj_contest_extension
-- ----------------------------
DROP TABLE IF EXISTS `oj_contest_extension`;
CREATE TABLE `oj_contest_extension` (
  `ce_id` bigint(20) unsigned NOT NULL AUTO_INCREMENT COMMENT '主键',
  `ce_gmt_create` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `ce_gmt_modified` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '修改时间',
  `ce_is_deleted` tinyint(4) unsigned NOT NULL DEFAULT '0' COMMENT '是否删除, 0.否, 1.是',
  `ce_version` int(10) unsigned NOT NULL DEFAULT '0' COMMENT '乐观锁字段',
  `ct_id` bigint(20) unsigned NOT NULL COMMENT '比赛id',
  `ce_key` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `ce_value` text COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`ce_id`),
  KEY `idx_ct_id_key` (`ct_id`,`ce_key`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='比赛拓展表';

-- ----------------------------
-- Records of oj_contest_extension
-- ----------------------------

-- ----------------------------
-- Table structure for oj_file
-- ----------------------------
DROP TABLE IF EXISTS `oj_file`;
CREATE TABLE `oj_file` (
  `f_id` bigint(20) unsigned NOT NULL COMMENT '主键',
  `f_gmt_create` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `f_gmt_modified` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '修改时间',
  `f_features` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT '特性字段',
  `f_is_deleted` tinyint(4) unsigned NOT NULL DEFAULT '0' COMMENT '是否删除, 0.否, 1.是',
  `u_id` bigint(20) unsigned NOT NULL COMMENT '用户id',
  `f_size` bigint(11) unsigned NOT NULL COMMENT '文件大小, 单位: B',
  `f_is_public` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '1' COMMENT '是否公开',
  `f_md5` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '文件md5',
  `f_name` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT '文件名',
  `f_extension_name` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT '文件拓展名',
  PRIMARY KEY (`f_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------
-- Records of oj_file
-- ----------------------------

-- ----------------------------
-- Table structure for oj_group
-- ----------------------------
DROP TABLE IF EXISTS `oj_group`;
CREATE TABLE `oj_group` (
  `g_id` bigint(20) unsigned NOT NULL AUTO_INCREMENT COMMENT '主键',
  `g_gmt_create` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `g_gmt_modified` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '修改时间',
  `g_features` varchar(512) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT '特性字段',
  `g_is_deleted` tinyint(4) unsigned NOT NULL DEFAULT '0' COMMENT '是否删除, 0.否, 1.是',
  `g_version` int(10) unsigned NOT NULL DEFAULT '0' COMMENT '乐观锁字段',
  `u_id` bigint(20) unsigned NOT NULL COMMENT '创建人',
  `g_title` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '课程标题',
  `g_year_semester` char(16) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '年与学期, 例如2019-2020-1',
  `g_gmt_start` datetime NOT NULL COMMENT '开始时间',
  `g_gmt_end` datetime NOT NULL COMMENT '结束时间',
  `g_markdown` text COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '课程说明',
  `g_participant_num` mediumint(9) unsigned NOT NULL DEFAULT '0' COMMENT '参加人数',
  `g_participants` text COLLATE utf8mb4_unicode_ci COMMENT '参加者集合',
  PRIMARY KEY (`g_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='课程信息表';

-- ----------------------------
-- Records of oj_group
-- ----------------------------

-- ----------------------------
-- Table structure for oj_judge_template
-- ----------------------------
DROP TABLE IF EXISTS `oj_judge_template`;
CREATE TABLE `oj_judge_template` (
  `jt_id` bigint(20) unsigned NOT NULL AUTO_INCREMENT COMMENT '主键',
  `jt_gmt_create` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `jt_gmt_modified` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '修改时间',
  `jt_features` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT '特性字段',
  `jt_is_deleted` tinyint(4) unsigned NOT NULL DEFAULT '0' COMMENT '是否删除, 0.否, 1.是',
  `jt_is_public` tinyint(4) unsigned NOT NULL DEFAULT '1' COMMENT '是否公开, 0.否, 1.是',
  `u_id` bigint(20) unsigned NOT NULL COMMENT '添加者id',
  `f_id` bigint(20) unsigned DEFAULT NULL COMMENT '评测模板支撑素材zip包id',
  `jt_version` int(10) unsigned NOT NULL DEFAULT '0' COMMENT '乐观锁字段',
  `jt_type` tinyint(3) unsigned NOT NULL COMMENT '评测模板类型',
  `jt_title` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '标题, 对外呈现',
  `jt_shell_script` text COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '评测模板',
  `jt_accept_file_extensions` varchar(48) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '评测模板可接受的文件后缀名',
  `jt_remote_oj` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT '远程oj',
  `jt_remote_parameters` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT '' COMMENT '远程oj提交参数',
  `jt_comment` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT '模板注释',
  PRIMARY KEY (`jt_id`),
  KEY `idx_title` (`jt_title`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------
-- Records of oj_judge_template
-- ----------------------------
INSERT INTO `oj_judge_template` VALUES ('1', '2020-10-23 11:29:38', '2020-11-17 04:35:20', '', '0', '1', '1', null, '1', '0', 'C++11', '{\n	\"user\": {\n		\"compile\": {\n			\"srcName\": \"solution.cc\",\n			\"maxCpuTime\": 3000,\n			\"maxRealTime\": 5000,\n			\"maxMemory\":  262144,\n			\"commands\": [\n				\"/usr/bin/g++ -DONLINE_JUDGE -O2 -w -fmax-errors=3 -std=c++11 solution.cc -lm -o solution\"\n			]\n		},\n		\"run\": {\n			\"command\": \"solution\",\n			\"seccompRules\": \"c_cpp\"\n		}\n	}\n}', 'cc,cpp', '', '', 'c++11 IO 评测模板');
INSERT INTO `oj_judge_template` VALUES ('2', '2020-11-16 08:05:44', '2020-11-16 08:46:00', '', '0', '1', '1', null, '1', '0', 'Python3', '{\n	\"user\": {\n  	\"compile\": {\n    	\"srcName\": \"solution.py\",\n      \"maxCpuTime\": 3000,\n      \"maxRealTime\": 5000,\n      \"maxMemory\": 262144,\n      \"commands\": [\n      	\"/usr/bin/python3 -m py_compile solution.py\"\n      ]\n    },\n    \"run\": {\n    	\"command\": \"/usr/bin/python3 __pycache__/solution.cpython-36.pyc\",\n      \"seccompRules\": \"general\",\n      \"maxRealTimeFactor\": 2,\n      \"maxCpuTimeFactor\": 2\n    }\n  }\n}', 'py', '', '', 'Python3 IO 评测模板');
INSERT INTO `oj_judge_template` VALUES ('3', '2020-11-16 08:17:00', '2020-11-16 08:46:22', '', '0', '1', '1', null, '1', '0', 'Python2', '{\n	\"user\": {\n  	\"compile\": {\n    	\"srcName\": \"solution.py\",\n      \"maxCpuTime\": 3000,\n      \"maxRealTime\": 5000,\n      \"maxMemory\": 262144,\n      \"commands\": [\n      	\"/usr/bin/python -m py_compile solution.py\"\n      ]\n    },\n    \"run\": {\n    	\"command\": \"/usr/bin/python solution.pyc\",\n      \"seccompRules\": \"general\",\n      \"maxRealTimeFactor\": 2,\n      \"maxCpuTimeFactor\": 2\n    }\n  }\n}', 'py', '', '', 'Python2 IO 评测模板');
INSERT INTO `oj_judge_template` VALUES ('4', '2020-11-16 08:45:23', '2020-11-16 11:17:25', '', '0', '1', '1', null, '1', '0', 'Java', '{\n	\"user\": {\n  	\"compile\": {\n    	\"srcName\": \"Main.java\",\n      \"maxCpuTime\": 3000,\n      \"maxRealTime\": 5000,\n      \"maxMemory\": 0,\n      \"commands\": [\n      	\"/usr/bin/javac Main.java -encoding UTF8\"\n      ]\n    },\n    \"run\": {\n    	\"command\": \"/usr/bin/java -XX:MaxRAM={problemMemoryLimit}k -Djava.security.manager -Djava.awt.headless=true Main\",\n      \"seccompRules\": \"general\",\n      \"maxMemoryFactor\": 0,\n      \"maxCpuTimeFactor\": 2,\n      \"maxRealTimeFactor\": 2\n    }\n  }\n}', 'java', '', '', 'Java IO 评测模板');

-- ----------------------------
-- Table structure for oj_problem
-- ----------------------------
DROP TABLE IF EXISTS `oj_problem`;
CREATE TABLE `oj_problem` (
  `p_id` bigint(20) unsigned NOT NULL AUTO_INCREMENT COMMENT '主键',
  `p_gmt_create` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `p_gmt_modified` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '修改时间',
  `p_features` varchar(2048) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT '特性字段',
  `p_version` int(10) unsigned NOT NULL DEFAULT '0' COMMENT '乐观锁字段',
  `p_is_deleted` tinyint(4) unsigned NOT NULL DEFAULT '0' COMMENT '是否删除, 0.否, 1.是',
  `p_code` varchar(32) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '题目编码',
  `p_is_public` tinyint(4) unsigned NOT NULL DEFAULT '0' COMMENT '题目公开在题库, 0否, 1是',
  `u_id` bigint(20) unsigned NOT NULL COMMENT '题目添加者id',
  `p_title` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '题目名称',
  `p_source` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT '题目来源描述',
  `p_remote_oj` varchar(16) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'vj名, 空串则为本地题目',
  `p_remote_url` varchar(256) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'vj题目链接',
  `p_submit_num` int(9) unsigned NOT NULL DEFAULT '0' COMMENT '题目提交数',
  `p_accept_num` int(9) unsigned NOT NULL DEFAULT '0' COMMENT '题目通过数',
  `p_languages` varchar(512) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '题目支持语言',
  `p_memory_limit` int(8) unsigned NOT NULL DEFAULT '256' COMMENT '内存限制, 单位KB',
  `p_time_limit` int(8) unsigned NOT NULL DEFAULT '1000' COMMENT '时间限制, 单位ms',
  `p_default_pd_id` bigint(20) unsigned DEFAULT NULL COMMENT '默认题目描述id',
  `p_checkpoint_num` int(9) unsigned NOT NULL DEFAULT '0',
  `p_judge_templates` varchar(512) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT '评测模板id集',
  `p_checkpoints` blob COMMENT '测试点id集, 二进制, (checkpointId, checkpointScore)',
  `p_checkpoint_cases` blob COMMENT '检查点样例 (checkpointId)',
  PRIMARY KEY (`p_id`),
  UNIQUE KEY `uk_problem_code` (`p_code`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=1000 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='题目表';

-- ----------------------------
-- Records of oj_problem
-- ----------------------------

-- ----------------------------
-- Table structure for oj_problem_description
-- ----------------------------
DROP TABLE IF EXISTS `oj_problem_description`;
CREATE TABLE `oj_problem_description` (
  `pd_id` bigint(20) unsigned NOT NULL AUTO_INCREMENT COMMENT '主键',
  `pd_gmt_create` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `pd_gmt_modified` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '修改时间',
  `pd_features` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT '特性字段',
  `pd_version` int(10) unsigned NOT NULL DEFAULT '0' COMMENT '乐观锁字段',
  `pd_is_deleted` tinyint(4) unsigned NOT NULL DEFAULT '0' COMMENT '是否删除, 0.否, 1.是',
  `pd_is_public` tinyint(4) unsigned NOT NULL DEFAULT '0' COMMENT '公开, 0否, 1是',
  `p_id` bigint(20) unsigned NOT NULL COMMENT '题目id',
  `u_id` bigint(20) unsigned NOT NULL COMMENT '创建者id',
  `pd_vote_num` int(11) NOT NULL DEFAULT '0' COMMENT '点赞数',
  `pd_title` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '',
  `pd_markdown_description` text COLLATE utf8mb4_unicode_ci COMMENT 'markdown描述',
  `pd_html_description` text COLLATE utf8mb4_unicode_ci COMMENT 'html描述',
  `pd_html_input` text COLLATE utf8mb4_unicode_ci COMMENT '输入',
  `pd_html_output` text COLLATE utf8mb4_unicode_ci COMMENT '输出',
  `pd_html_sample_input` text COLLATE utf8mb4_unicode_ci COMMENT '样例输入',
  `pd_html_sample_outout` text COLLATE utf8mb4_unicode_ci COMMENT '样例输出',
  `pd_html_hint` text COLLATE utf8mb4_unicode_ci COMMENT '提示',
  PRIMARY KEY (`pd_id`),
  KEY `idx_p_id` (`p_id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='题目描述表';

-- ----------------------------
-- Records of oj_problem_description
-- ----------------------------

-- ----------------------------
-- Table structure for oj_problem_extension
-- ----------------------------
DROP TABLE IF EXISTS `oj_problem_extension`;
CREATE TABLE `oj_problem_extension` (
  `pe_id` bigint(20) unsigned NOT NULL AUTO_INCREMENT COMMENT '主键',
  `pe_gmt_create` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `pe_gmt_modified` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '修改时间',
  `pe_is_deleted` tinyint(4) unsigned NOT NULL DEFAULT '0' COMMENT '是否删除, 0.否, 1.是',
  `pe_version` int(10) unsigned NOT NULL DEFAULT '0' COMMENT '乐观锁字段',
  `p_id` bigint(20) unsigned NOT NULL COMMENT '题目id',
  `pe_key` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `pe_value` text COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`pe_id`),
  UNIQUE KEY `uk_p_id_key` (`p_id`,`pe_key`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='比赛拓展表';

-- ----------------------------
-- Records of oj_problem_extension
-- ----------------------------

-- ----------------------------
-- Table structure for oj_submission
-- ----------------------------
DROP TABLE IF EXISTS `oj_submission`;
CREATE TABLE `oj_submission` (
  `s_id` bigint(20) unsigned NOT NULL COMMENT '主键, 分布式id',
  `s_gmt_create` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `s_gmt_modified` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '修改时间',
  `s_features` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT '特性字段',
  `s_version` int(10) unsigned NOT NULL DEFAULT '0' COMMENT '乐观锁字段',
  `s_is_public` tinyint(4) NOT NULL DEFAULT '0' COMMENT '是否公开, 0不公开, 1公开',
  `s_valid` tinyint(4) unsigned NOT NULL DEFAULT '1' COMMENT '有效提交, 0无效, 1有效',
  `p_id` bigint(20) unsigned NOT NULL COMMENT '题目id',
  `u_id` bigint(20) unsigned NOT NULL COMMENT '提交者id',
  `ct_id` bigint(20) unsigned NOT NULL DEFAULT '0' COMMENT '关联的比赛id',
  `jt_id` bigint(20) unsigned NOT NULL COMMENT '评测模板id',
  `f_id` bigint(20) unsigned DEFAULT NULL COMMENT 'zipFile主键',
  `s_language` varchar(16) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '评测模板, 比如C++、Python等',
  `s_ipv4` char(16) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '提交端ipv4',
  `s_judger_id` bigint(20) DEFAULT NULL COMMENT '评测机id, 外键于u_id',
  `s_judge_result` tinyint(4) NOT NULL DEFAULT '0' COMMENT '评测结果',
  `s_judge_score` int(4) unsigned NOT NULL DEFAULT '0' COMMENT '评测分数',
  `s_used_time` int(8) unsigned DEFAULT NULL COMMENT '使用时间, 单位ms',
  `s_used_memory` int(8) unsigned DEFAULT NULL COMMENT '使用内存, 单位KB',
  `s_code_length` int(11) unsigned NOT NULL COMMENT '代码长度/字符数, 单位B',
  `s_judge_log` text COLLATE utf8mb4_unicode_ci COMMENT '评测结果文案, 展示到前台',
  `s_code` text COLLATE utf8mb4_unicode_ci COMMENT '提交代码',
  `s_checkpoint_results` blob COMMENT '检查点测试结果, 二进制, (int judge_result, int judge_time, int judge_memory)集',
  PRIMARY KEY (`s_id`),
  KEY `idx_contest` (`ct_id`) USING BTREE,
  KEY `idx_problem` (`p_id`) USING BTREE,
  KEY `idx_user` (`u_id`) USING BTREE,
  KEY `idx_contest_user_problem` (`ct_id`,`u_id`,`p_id`) USING BTREE,
  KEY `idx_contest_problem_user` (`ct_id`,`p_id`,`u_id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='题库提交表';

-- ----------------------------
-- Records of oj_submission
-- ----------------------------

-- ----------------------------
-- Table structure for oj_submission_extension
-- ----------------------------
DROP TABLE IF EXISTS `oj_submission_extension`;
CREATE TABLE `oj_submission_extension` (
  `se_id` bigint(20) unsigned NOT NULL AUTO_INCREMENT COMMENT '主键',
  `se_gmt_create` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `se_gmt_modified` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '修改时间',
  `s_id` bigint(20) unsigned NOT NULL COMMENT '提交id',
  `se_key` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `se_value` text COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`se_id`),
  UNIQUE KEY `uk_s_id_key` (`s_id`,`se_key`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='提交拓展表';

-- ----------------------------
-- Records of oj_submission_extension
-- ----------------------------

-- ----------------------------
-- Table structure for oj_tag
-- ----------------------------
DROP TABLE IF EXISTS `oj_tag`;
CREATE TABLE `oj_tag` (
  `t_id` bigint(20) unsigned NOT NULL AUTO_INCREMENT COMMENT '主键',
  `t_gmt_create` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `t_gmt_modified` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '修改时间',
  `t_features` varchar(96) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT '特性字段',
  `t_is_deleted` tinyint(4) unsigned NOT NULL DEFAULT '0' COMMENT '是否删除, 0.否, 1.是',
  `t_parent_id` bigint(20) unsigned NOT NULL DEFAULT '0' COMMENT '父节点id',
  `t_title` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '标签内容',
  PRIMARY KEY (`t_id`),
  KEY `idx_title` (`t_title`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='题目标签表';

-- ----------------------------
-- Records of oj_tag
-- ----------------------------
INSERT INTO `oj_tag` VALUES ('1', '2020-10-01 03:33:28', '2020-10-01 03:33:28', '', '0', '0', 'DP');
INSERT INTO `oj_tag` VALUES ('2', '2020-10-01 03:33:42', '2020-10-01 03:33:42', '', '0', '1', '树形DP');
INSERT INTO `oj_tag` VALUES ('3', '2020-10-01 03:34:00', '2020-10-01 03:34:00', '', '0', '1', '数位DP');
INSERT INTO `oj_tag` VALUES ('4', '2020-10-11 05:53:32', '2020-10-11 06:38:14', '', '0', '0', '超级超级dp');

-- ----------------------------
-- Table structure for oj_url_permission
-- ----------------------------
DROP TABLE IF EXISTS `oj_url_permission`;
CREATE TABLE `oj_url_permission` (
  `up_id` bigint(20) unsigned NOT NULL AUTO_INCREMENT COMMENT '主键',
  `up_gmt_create` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `up_gmt_modified` datetime NOT NULL COMMENT '修改时间',
  `up_features` varchar(512) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT '特性字段',
  `up_is_deleted` tinyint(4) unsigned NOT NULL DEFAULT '0' COMMENT '是否删除, 0.否, 1.是',
  `up_version` int(10) unsigned NOT NULL DEFAULT '0' COMMENT '乐观锁字段',
  `up_url` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '权限url',
  `up_name` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `up_roles` varchar(256) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'superadmin' COMMENT '权限角色',
  PRIMARY KEY (`up_id`),
  UNIQUE KEY `uk_url` (`up_url`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=84 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------
-- Records of oj_url_permission
-- ----------------------------
INSERT INTO `oj_url_permission` VALUES ('1', '2020-09-26 09:42:46', '2020-09-26 09:42:46', '', '0', '0', '/judger/checkpoint/download', '', 'superadmin');
INSERT INTO `oj_url_permission` VALUES ('2', '2020-09-26 09:42:46', '2020-09-26 09:42:46', '', '0', '0', '/manage/checkpoint/query', '', 'superadmin,admin');
INSERT INTO `oj_url_permission` VALUES ('3', '2020-09-26 09:42:46', '2020-09-26 09:42:46', '', '0', '0', '/manage/checkpoint/download', '', 'superadmin,admin');
INSERT INTO `oj_url_permission` VALUES ('4', '2020-09-26 09:42:46', '2020-09-26 09:42:46', '', '0', '0', '/manage/checkpoint/list', '', 'superadmin,admin');
INSERT INTO `oj_url_permission` VALUES ('5', '2020-09-26 09:42:46', '2020-09-26 09:42:46', '', '0', '0', '/manage/checkpoint/uploadFiles', '检查点多文件上传', 'superadmin,admin');
INSERT INTO `oj_url_permission` VALUES ('6', '2020-09-26 09:42:46', '2020-09-26 09:42:46', '', '0', '0', '/manage/checkpoint/upload', '', 'superadmin,admin');
INSERT INTO `oj_url_permission` VALUES ('7', '2020-09-26 09:42:46', '2020-09-26 09:42:46', '', '0', '0', '/problem/list', '', 'all');
INSERT INTO `oj_url_permission` VALUES ('8', '2020-09-26 09:42:46', '2020-09-26 09:42:46', '', '0', '0', '/problem/query', '', 'all');
INSERT INTO `oj_url_permission` VALUES ('9', '2020-09-26 09:42:46', '2020-09-26 09:42:46', '', '0', '0', '/judger/problem/query', '', 'superadmin');
INSERT INTO `oj_url_permission` VALUES ('10', '2020-09-26 09:42:46', '2020-09-26 09:42:46', '', '0', '0', '/manage/problem/query', '', 'superadmin,admin');
INSERT INTO `oj_url_permission` VALUES ('11', '2020-09-26 09:42:46', '2020-09-26 09:42:46', '', '0', '0', '/manage/problem/create', '', 'superadmin,admin');
INSERT INTO `oj_url_permission` VALUES ('12', '2020-09-26 09:42:46', '2020-09-26 09:42:46', '', '0', '0', '/manage/problem/list', '', 'superadmin,admin');
INSERT INTO `oj_url_permission` VALUES ('13', '2020-09-26 09:42:46', '2020-09-26 09:42:46', '', '0', '0', '/manage/problem/update', '', 'superadmin,admin');
INSERT INTO `oj_url_permission` VALUES ('14', '2020-09-26 09:42:49', '2020-09-26 09:42:49', '', '0', '0', '/user/register', '', 'all');
INSERT INTO `oj_url_permission` VALUES ('15', '2020-09-26 09:42:49', '2020-09-26 09:42:49', '', '0', '0', '/user/login', '', 'all');
INSERT INTO `oj_url_permission` VALUES ('16', '2020-09-26 09:42:49', '2020-09-26 09:42:49', '', '0', '0', '/user/logout', '', 'all');
INSERT INTO `oj_url_permission` VALUES ('17', '2020-09-26 09:42:56', '2020-09-26 09:42:56', '', '0', '0', '/submit/query', '', 'all');
INSERT INTO `oj_url_permission` VALUES ('18', '2020-09-26 09:42:56', '2020-09-26 09:42:56', '', '0', '0', '/submit/create', '', 'user');
INSERT INTO `oj_url_permission` VALUES ('19', '2020-09-26 09:42:56', '2020-09-26 09:42:56', '', '0', '0', '/submit/list', '', 'all');
INSERT INTO `oj_url_permission` VALUES ('20', '2020-09-26 09:42:56', '2020-09-26 09:42:56', '', '0', '0', '/judger/submit/update', '', 'superadmin');
INSERT INTO `oj_url_permission` VALUES ('21', '2020-09-26 09:42:56', '2020-09-26 09:42:56', '', '0', '0', '/judger/submit/query', '', 'superadmin');
INSERT INTO `oj_url_permission` VALUES ('22', '2020-09-29 06:53:14', '2020-09-29 06:53:14', '', '0', '0', '/user/emailVerify', '', 'all');
INSERT INTO `oj_url_permission` VALUES ('23', '2020-09-29 07:54:08', '2020-09-29 07:54:08', '', '0', '0', '/user/resetPassword', '', 'all');
INSERT INTO `oj_url_permission` VALUES ('24', '2020-09-29 07:54:08', '2020-09-29 07:54:08', '', '0', '0', '/user/forgetPassword', '', 'all');
INSERT INTO `oj_url_permission` VALUES ('25', '2020-09-29 07:54:08', '2020-09-29 07:54:08', '', '0', '0', '/user/getProfile', '', 'all');
INSERT INTO `oj_url_permission` VALUES ('26', '2020-09-29 08:38:42', '2020-09-29 08:38:42', '', '0', '0', '/user/verifyEmail', '', 'all');
INSERT INTO `oj_url_permission` VALUES ('27', '2020-09-29 13:04:49', '2020-09-29 13:04:49', '', '0', '0', '/user/sendVerificationEmail', '', 'all');
INSERT INTO `oj_url_permission` VALUES ('28', '2020-10-01 01:12:51', '2020-10-01 01:12:51', '', '0', '0', '/manage/problem/createDescription', '', 'superadmin,admin');
INSERT INTO `oj_url_permission` VALUES ('29', '2020-10-01 12:57:39', '2020-10-01 12:57:39', '', '0', '0', '/user/getCaptcha', '', 'all');
INSERT INTO `oj_url_permission` VALUES ('30', '2020-10-01 13:30:54', '2020-10-01 13:30:54', '', '0', '0', '/user/isExist', '', 'all');
INSERT INTO `oj_url_permission` VALUES ('31', '2020-10-01 13:46:15', '2020-10-01 13:46:15', '', '0', '0', '/user/updateProfile', '', 'user');
INSERT INTO `oj_url_permission` VALUES ('34', '2020-10-02 10:46:59', '2020-10-02 10:46:59', '', '0', '0', '/site/getCopyright', '', 'all');
INSERT INTO `oj_url_permission` VALUES ('35', '2020-10-03 01:34:32', '2020-10-03 01:34:32', '', '0', '0', '/contest/query', '', 'user');
INSERT INTO `oj_url_permission` VALUES ('36', '2020-10-03 01:34:32', '2020-10-03 01:34:32', '', '0', '0', '/contest/list', '', 'all');
INSERT INTO `oj_url_permission` VALUES ('37', '2020-10-03 01:34:32', '2020-10-03 01:34:32', '', '0', '0', '/contest/participate', '', 'user');
INSERT INTO `oj_url_permission` VALUES ('38', '2020-10-03 01:34:32', '2020-10-03 01:34:32', '', '0', '0', '/manage/contest/create', '', 'superadmin,admin');
INSERT INTO `oj_url_permission` VALUES ('39', '2020-10-03 08:26:33', '2020-10-03 08:26:33', '', '0', '0', '/contest/queryUpcomingContest', '', 'all');
INSERT INTO `oj_url_permission` VALUES ('40', '2020-10-03 10:57:23', '2020-10-03 10:57:23', '', '0', '0', '/contest/queryProblem', '', 'user');
INSERT INTO `oj_url_permission` VALUES ('41', '2020-10-03 12:02:52', '2020-10-03 12:02:52', '', '0', '0', '/contest/createSubmission', '', 'user');
INSERT INTO `oj_url_permission` VALUES ('42', '2020-10-03 13:32:16', '2020-10-03 13:32:16', '', '0', '0', '/contest/listSubmission', '', 'user');
INSERT INTO `oj_url_permission` VALUES ('43', '2020-10-05 06:29:40', '2020-10-05 06:29:40', '', '0', '0', '/user/queryUserACProblem', '', 'user');
INSERT INTO `oj_url_permission` VALUES ('44', '2020-10-05 06:29:40', '2020-10-05 06:29:40', '', '0', '0', '/user/queryUserParticipateContest', '', 'user');
INSERT INTO `oj_url_permission` VALUES ('45', '2020-10-05 07:05:22', '2020-10-05 07:05:22', '', '0', '0', '/user/queryACProblem', '', 'user');
INSERT INTO `oj_url_permission` VALUES ('46', '2020-10-05 07:05:22', '2020-10-05 07:05:22', '', '0', '0', '/user/queryParticipateContest', '', 'user');
INSERT INTO `oj_url_permission` VALUES ('47', '2020-10-05 07:33:09', '2020-10-05 07:33:09', '', '0', '0', '/contest/queryACProblem', '', 'user');
INSERT INTO `oj_url_permission` VALUES ('48', '2020-10-05 12:57:15', '2020-10-05 20:59:11', '', '0', '0', '/ws/submission', '', 'user');
INSERT INTO `oj_url_permission` VALUES ('49', '2020-10-06 06:57:02', '2020-10-06 06:57:02', '', '0', '0', '/contest/querySubmission', '', 'user');
INSERT INTO `oj_url_permission` VALUES ('50', '2020-10-06 08:35:26', '2020-10-06 08:35:26', '', '0', '0', '/manage/user/update', '', 'superadmin,admin');
INSERT INTO `oj_url_permission` VALUES ('51', '2020-10-06 08:35:26', '2020-10-06 08:35:26', '', '0', '0', '/manage/user/list', '', 'superadmin,admin');
INSERT INTO `oj_url_permission` VALUES ('52', '2020-10-06 08:35:26', '2020-10-06 08:35:26', '', '0', '0', '/manage/user/addUsers', '', 'superadmin,admin');
INSERT INTO `oj_url_permission` VALUES ('53', '2020-10-07 13:37:45', '2020-10-07 13:37:45', '', '0', '0', '/manage/problem/updateDescription', '', 'superadmin,admin');
INSERT INTO `oj_url_permission` VALUES ('54', '2020-10-10 12:36:50', '2020-10-10 12:36:50', '', '0', '0', '/manage/problem/queryDescription', '', 'superadmin,admin');
INSERT INTO `oj_url_permission` VALUES ('55', '2020-10-10 12:36:50', '2020-10-10 12:36:50', '', '0', '0', '/manage/problem/queryDescriptionList', '', 'superadmin,admin');
INSERT INTO `oj_url_permission` VALUES ('56', '2020-10-10 12:37:17', '2020-10-10 12:37:17', '', '0', '0', '/contest/rank', '', 'user');
INSERT INTO `oj_url_permission` VALUES ('57', '2020-10-11 05:50:36', '2020-10-11 05:50:36', '', '0', '0', '/manage/tag/list', '', 'superadmin,admin');
INSERT INTO `oj_url_permission` VALUES ('58', '2020-10-11 05:50:36', '2020-10-11 05:50:36', '', '0', '0', '/manage/tag/create', '', 'superadmin,admin');
INSERT INTO `oj_url_permission` VALUES ('59', '2020-10-11 06:02:01', '2020-10-11 06:02:01', '', '0', '0', '/manage/tag/update', '', 'superadmin,admin');
INSERT INTO `oj_url_permission` VALUES ('60', '2020-10-12 06:23:51', '2020-10-12 06:23:51', '', '0', '0', '/manage/contest/query', '', 'superadmin,admin');
INSERT INTO `oj_url_permission` VALUES ('61', '2020-10-12 06:23:51', '2020-10-12 06:23:51', '', '0', '0', '/manage/contest/page', '', 'superadmin,admin');
INSERT INTO `oj_url_permission` VALUES ('62', '2020-10-12 06:31:04', '2020-10-12 06:31:04', '', '0', '0', '/manage/contest/update', '', 'superadmin,admin');
INSERT INTO `oj_url_permission` VALUES ('63', '2020-10-13 08:08:10', '2020-10-13 08:08:10', '', '0', '0', '/submit/queryACProblem', '', 'user');
INSERT INTO `oj_url_permission` VALUES ('67', '2020-10-19 14:15:01', '2020-10-19 14:15:01', '', '0', '0', '/filesys/zipDownload', '', 'superadmin,admin');
INSERT INTO `oj_url_permission` VALUES ('68', '2020-10-19 14:15:01', '2020-10-19 14:15:01', '', '0', '0', '/filesys/upload', '', 'superadmin,admin');
INSERT INTO `oj_url_permission` VALUES ('69', '2020-10-19 14:15:01', '2020-10-19 14:15:01', '', '0', '0', '/filesys/uploadFiles', '', 'superadmin,admin');
INSERT INTO `oj_url_permission` VALUES ('74', '2020-10-22 12:51:26', '2020-10-22 12:51:26', '', '0', '0', '/manage/judgetemplate/update', '', 'superadmin,admin');
INSERT INTO `oj_url_permission` VALUES ('75', '2020-10-22 12:51:26', '2020-10-22 12:51:26', '', '0', '0', '/manage/judgetemplate/create', '', 'superadmin,admin');
INSERT INTO `oj_url_permission` VALUES ('76', '2020-10-22 12:51:26', '2020-10-22 12:51:26', '', '0', '0', '/manage/judgetemplate/query', '', 'superadmin,admin');
INSERT INTO `oj_url_permission` VALUES ('77', '2020-10-22 12:51:26', '2020-10-22 12:51:26', '', '0', '0', '/manage/judgetemplate/page', '', 'superadmin,admin');
INSERT INTO `oj_url_permission` VALUES ('78', '2020-10-24 10:28:42', '2020-10-24 10:28:42', '', '0', '0', '/filesys/queryByMd5', '', 'superadmin,admin');
INSERT INTO `oj_url_permission` VALUES ('79', '2020-10-24 10:36:54', '2020-10-24 10:36:54', '', '0', '0', '/manage/judgetemplate/listByTitle', '', 'superadmin,admin');
INSERT INTO `oj_url_permission` VALUES ('80', '2020-11-13 05:08:35', '2020-11-13 05:08:35', '', '0', '0', '/submit/rejudge', '', 'superadmin');
INSERT INTO `oj_url_permission` VALUES ('81', '2020-11-20 11:16:16', '2020-11-20 11:16:16', '', '0', '0', '/contest/invalidateSubmission', '', 'superadmin,admin');
INSERT INTO `oj_url_permission` VALUES ('82', '2020-11-20 11:48:08', '2020-11-20 11:48:08', '', '0', '0', '/submit/invalidateSubmission', '', 'superadmin,admin');
INSERT INTO `oj_url_permission` VALUES ('83', '2020-11-21 11:09:15', '2020-11-21 11:09:15', '', '0', '0', '/manage/user/delete', '', 'superadmin');

-- ----------------------------
-- Table structure for oj_user
-- ----------------------------
DROP TABLE IF EXISTS `oj_user`;
CREATE TABLE `oj_user` (
  `u_id` bigint(20) unsigned NOT NULL AUTO_INCREMENT COMMENT '用户id',
  `u_gmt_create` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `u_gmt_modified` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '修改时间',
  `u_features` varchar(2048) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT '特性字段, 用于用户打标, 拓展属性如过题记录请使用ext表',
  `u_is_deleted` tinyint(4) unsigned NOT NULL DEFAULT '0' COMMENT '是否删除, 0.否, 1.是',
  `u_version` int(10) unsigned NOT NULL DEFAULT '0' COMMENT '乐观锁字段',
  `u_username` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '用户账号, 英文、数字、下划线组成',
  `u_nickname` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'nickname' COMMENT '用户昵称',
  `u_salt` char(32) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '密码加盐',
  `u_password` varchar(40) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '用户密码',
  `u_email` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '用户邮箱',
  `u_is_email_verified` tinyint(4) NOT NULL DEFAULT '0' COMMENT '邮箱已验证, 0未验证, 1已验证',
  `u_phone` char(16) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' COMMENT '手机号码',
  `u_gender` tinyint(4) NOT NULL DEFAULT '2' COMMENT '用户性别, 0.女, 1.男, 2.问号',
  `u_student_id` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT '' COMMENT '学生学号',
  `u_roles` varchar(256) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '用户角色，'','' 号分割',
  PRIMARY KEY (`u_id`),
  UNIQUE KEY `uk_username` (`u_username`) USING BTREE,
  UNIQUE KEY `uk_email` (`u_email`) USING HASH
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户信息表';

-- ----------------------------
-- Records of oj_user
-- ----------------------------
INSERT INTO `oj_user` VALUES ('1', '2020-10-21 08:21:34', '2020-10-21 08:21:34', '', '0', '0', 'superadmin', 'superadmin', '2f34921ecdf24f9f9855d3c4159cb440', '4cec29c23a40937a8199aaf322bfed51', 'sdu_oj@163.com', '1', '', '2', 'superadmin', 'superadmin,admin,user');

-- ----------------------------
-- Table structure for oj_user_extension
-- ----------------------------
DROP TABLE IF EXISTS `oj_user_extension`;
CREATE TABLE `oj_user_extension` (
  `ue_id` bigint(20) unsigned NOT NULL AUTO_INCREMENT COMMENT '主键',
  `ue_gmt_create` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `ue_gmt_modified` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '修改时间',
  `ue_version` int(10) unsigned NOT NULL DEFAULT '0' COMMENT '乐观锁字段',
  `ue_is_deleted` tinyint(4) unsigned NOT NULL DEFAULT '0' COMMENT '是否删除, 0.否, 1.是',
  `u_id` bigint(20) unsigned NOT NULL COMMENT '用户id',
  `ue_key` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `ue_value` text COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`ue_id`),
  UNIQUE KEY `uk_u_id_key` (`u_id`,`ue_key`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户拓展表';

-- ----------------------------
-- Records of oj_user_extension
-- ----------------------------

-- ----------------------------
-- Table structure for oj_user_session
-- ----------------------------
DROP TABLE IF EXISTS `oj_user_session`;
CREATE TABLE `oj_user_session` (
  `us_id` bigint(20) unsigned NOT NULL AUTO_INCREMENT COMMENT '主键',
  `us_gmt_create` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `us_gmt_modified` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '修改时间',
  `us_features` varchar(32) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '特性字段, 用于用户打标, 拓展属性如过题记录请使用ext表',
  `u_username` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '用户账号',
  `us_ipv4` char(16) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '登陆端ipv4',
  `us_user_agent` varchar(160) COLLATE utf8mb4_unicode_ci NOT NULL,
  `us_is_success` tinyint(4) unsigned NOT NULL COMMENT '是否登陆成功, 0.不成功, 1.成功',
  PRIMARY KEY (`us_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户会话表';

-- ----------------------------
-- Records of oj_user_session
-- ----------------------------

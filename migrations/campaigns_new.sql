USE cardanoism;

CREATE TABLE `campaigns_new` (
  `id` char(36) NOT NULL,
  `fund_uuid` char(36) DEFAULT NULL,
  `title` varchar(255) NOT NULL,
  `title_jp` varchar(255) DEFAULT NULL,
  `slug` varchar(255) NOT NULL,
  `excerpt` text DEFAULT NULL,
  `excerpt_jp` text DEFAULT NULL,
  `amount` decimal(20,2) NOT NULL,
  `launched_at` datetime(6) DEFAULT NULL,
  `awarded_at` datetime(6) DEFAULT NULL,
  `color` varchar(32) DEFAULT NULL,
  `label` varchar(255) NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

import React, { useState } from 'react';
import {
  Box,
  Typography,
  Paper,
  Grid,
  Card,
  CardContent,
  Button,
  Chip,
  Divider,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Link,
  Alert,
  AlertTitle,
  Breadcrumbs,
  Stepper,
  Step,
  StepLabel,
  StepContent,
} from '@mui/material';
import {
  ExpandMore as ExpandMoreIcon,
  Code as CodeIcon,
  Architecture as ArchitectureIcon,
  Security as SecurityIcon,
  Speed as SpeedIcon,
  Storage as StorageIcon,
  Cloud as CloudIcon,
  BugReport as BugReportIcon,
  Rocket as RocketIcon,
  School as SchoolIcon,
  GitHub as GitHubIcon,
  Article as ArticleIcon,
  Build as BuildIcon,
  Api as ApiIcon,
  Dashboard as DashboardIcon,
  ArrowBack as ArrowBackIcon,
  CheckCircle as CheckCircleIcon,
  Storage as DockerIcon,
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';

const DeploymentGuide: React.FC = () => {
  const navigate = useNavigate();
  const [expandedSection, setExpandedSection] = useState<string | false>('overview');

  const handleChange = (panel: string) => (event: React.SyntheticEvent, isExpanded: boolean) => {
    setExpandedSection(isExpanded ? panel : false);
  };

  const deploymentEnvironments = [
    {
      name: "开发环境",
      description: "本地开发环境",
      requirements: {
        cpu: "2 核",
        ram: "4GB",
        storage: "20GB SSD",
        network: "100 Mbps"
      },
      services: ["PostgreSQL", "Redis", "Milvus", "模型服务"],
      status: "✅ 就绪"
    },
    {
      name: "预发布环境",
      description: "生产前测试环境",
      requirements: {
        cpu: "4 核",
        ram: "8GB",
        storage: "50GB SSD",
        network: "1 Gbps"
      },
      services: ["PostgreSQL", "Redis", "Milvus", "模型服务", "Prometheus", "Grafana"],
      status: "✅ 就绪"
    },
    {
      name: "生产环境",
      description: "具备高可用性的生产环境",
      requirements: {
        cpu: "8 核以上",
        ram: "16GB+",
        storage: "100GB+ SSD",
        network: "10 Gbps"
      },
      services: ["PostgreSQL 集群", "Redis 集群", "Milvus 集群", "模型服务", "完整监控栈", "负载均衡器"],
      status: "🔄 进行中"
    }
  ];

  const deploymentMethods = [
    {
      name: "Docker Compose",
      description: "适用于开发和小型生产环境的简单容器化部署",
      pros: ["易于设置", "单命令部署", "适合开发"],
      cons: ["仅支持单节点", "扩展性有限", "不具备高可用性"],
      commands: [
        "docker compose up -d",
        "docker compose logs -f",
        "docker compose down"
      ],
      status: "✅ 可用"
    },
  ];

  const deploymentSteps = [
    {
      label: "前提条件",
      description: "安装所需软件和依赖项",
      content: [
        "安装 Docker 和 Docker Compose",
        "设置 GPU 驱动程序（用于 Milvus）",
        "配置模型服务 API 密钥"
      ]
    },
    {
      label: "配置",
      description: "配置环境变量和设置",
      content: [
        "将 .env.example 复制为 .env",
        "设置数据库凭据",
        "配置模型服务 API 密钥",
        "设置监控端点",
        "配置安全设置"
      ]
    },
    {
      label: "数据库设置",
      description: "初始化数据库并运行迁移",
      content: [
        "启动 PostgreSQL/TimescaleDB",
        "运行数据库迁移",
        "初始化 Milvus 集合",
        "设置 Redis 配置",
        "验证数据库连接"
      ]
    },
    {
      label: "服务部署",
      description: "部署应用服务",
      content: [
        "部署核心服务（API、智能体）",
        "部署 MCP 框架",
        "部署监控栈",
        "部署前端应用",
        "验证所有服务均在运行"
      ]
    },
    {
      label: "健康检查",
      description: "验证部署并运行健康检查",
      content: [
        "检查 API 健康端点",
        "验证智能体功能",
        "测试 MCP 工具发现",
        "检查监控仪表板",
        "运行集成测试"
      ]
    }
  ];

  const monitoringSetup = [
    {
      service: "Prometheus",
      description: "指标收集与存储",
      port: 9090,
      config: "monitoring/prometheus/prometheus.yml",
      status: "✅ 已配置"
    },
    {
      service: "Grafana",
      description: "可视化与仪表板",
      port: 3000,
      config: "monitoring/grafana/dashboards/",
      status: "✅ 已配置"
    },
    {
      service: "Alertmanager",
      description: "告警路由与通知",
      port: 9093,
      config: "monitoring/alertmanager/alertmanager.yml",
      status: "✅ 已配置"
    },
    {
      service: "Node Exporter",
      description: "系统指标收集",
      port: 9100,
      config: "内置",
      status: "✅ 已配置"
    }
  ];

  return (
    <Box sx={{ p: 3, maxWidth: 1200, mx: 'auto' }}>
      {/* Breadcrumbs */}
      <Breadcrumbs sx={{ mb: 2 }}>
        <Button startIcon={<ArrowBackIcon />} onClick={() => navigate('/documentation')}>
          文档
        </Button>
        <Typography color="text.primary">部署指南</Typography>
      </Breadcrumbs>

      {/* Header */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h3" component="h1" gutterBottom sx={{ fontWeight: 'bold', color: 'primary.main' }}>
          部署指南
        </Typography>
        <Typography variant="h5" component="h2" gutterBottom color="text.secondary">
          生产部署说明
        </Typography>
        <Typography variant="body1" sx={{ mb: 2 }}>
          在不同环境中部署多智能体智慧仓储系统的完整指南。
          本指南涵盖带监控和安全配置的 Docker Compose 部署。
        </Typography>
        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mb: 3 }}>
          <Chip label="Docker" color="primary" />
          <Chip label="生产就绪" color="success" />
          <Chip label="监控" color="warning" />
        </Box>
      </Box>

      {/* Status Alert */}
      <Alert severity="info" sx={{ mb: 4 }}>
        <AlertTitle>🚀 多种部署选项</AlertTitle>
        系统支持多种部署方式，包括适用于开发环境的简单 Docker Compose 部署，
        也可用于生产环境。
      </Alert>

      {/* Deployment Environments */}
      <Accordion expanded={expandedSection === 'environments'} onChange={handleChange('environments')}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <CloudIcon color="primary" />
            部署环境
          </Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Grid container spacing={3}>
            {deploymentEnvironments.map((env, index) => (
              <Grid item xs={12} md={4} key={index}>
                <Card variant="outlined" sx={{ height: '100%' }}>
                  <CardContent>
                    <Typography variant="h6" gutterBottom>
                      {env.name}
                    </Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                      {env.description}
                    </Typography>
                    <Box sx={{ mb: 2 }}>
                      <Typography variant="subtitle2" gutterBottom>要求：</Typography>
                      <List dense>
                        <ListItem sx={{ py: 0 }}>
                          <ListItemText primary={`CPU: ${env.requirements.cpu}`} primaryTypographyProps={{ variant: 'body2' }} />
                        </ListItem>
                        <ListItem sx={{ py: 0 }}>
                          <ListItemText primary={`RAM: ${env.requirements.ram}`} primaryTypographyProps={{ variant: 'body2' }} />
                        </ListItem>
                        <ListItem sx={{ py: 0 }}>
                          <ListItemText primary={`存储：${env.requirements.storage}`} primaryTypographyProps={{ variant: 'body2' }} />
                        </ListItem>
                        <ListItem sx={{ py: 0 }}>
                          <ListItemText primary={`网络：${env.requirements.network}`} primaryTypographyProps={{ variant: 'body2' }} />
                        </ListItem>
                      </List>
                    </Box>
                    <Box sx={{ mb: 2 }}>
                      <Typography variant="subtitle2" gutterBottom>服务：</Typography>
                      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                        {env.services.map((service, serviceIndex) => (
                          <Chip key={serviceIndex} label={service} size="small" variant="outlined" />
                        ))}
                      </Box>
                    </Box>
                    <Chip 
                      label={env.status} 
                      color={env.status.includes('✅') ? 'success' : 'warning'}
                      size="small"
                    />
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </AccordionDetails>
      </Accordion>

      {/* Deployment Methods */}
      <Accordion expanded={expandedSection === 'methods'} onChange={handleChange('methods')}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <BuildIcon color="primary" />
            部署方式
          </Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Grid container spacing={3}>
            {deploymentMethods.map((method, index) => (
              <Grid item xs={12} md={4} key={index}>
                <Card variant="outlined" sx={{ height: '100%' }}>
                  <CardContent>
                    <Typography variant="h6" gutterBottom>
                      {method.name}
                    </Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                      {method.description}
                    </Typography>
                    <Box sx={{ mb: 2 }}>
                      <Typography variant="subtitle2" gutterBottom>优点：</Typography>
                      <List dense>
                        {method.pros.map((pro, proIndex) => (
                          <ListItem key={proIndex} sx={{ py: 0 }}>
                            <ListItemIcon>
                              <CheckCircleIcon fontSize="small" color="success" />
                            </ListItemIcon>
                            <ListItemText primary={pro} primaryTypographyProps={{ variant: 'body2' }} />
                          </ListItem>
                        ))}
                      </List>
                    </Box>
                    <Box sx={{ mb: 2 }}>
                      <Typography variant="subtitle2" gutterBottom>命令：</Typography>
                      {method.commands.map((command, cmdIndex) => (
                        <Paper key={cmdIndex} sx={{ p: 1, bgcolor: 'grey.100', fontFamily: 'monospace', fontSize: '0.75rem', mb: 1 }}>
                          {command}
                        </Paper>
                      ))}
                    </Box>
                    <Chip 
                      label={method.status} 
                      color={method.status.includes('✅') ? 'success' : 'warning'}
                      size="small"
                    />
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </AccordionDetails>
      </Accordion>

      {/* Deployment Steps */}
      <Accordion expanded={expandedSection === 'steps'} onChange={handleChange('steps')}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <RocketIcon color="primary" />
            分步部署
          </Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Stepper orientation="vertical">
            {deploymentSteps.map((step, index) => (
              <Step key={step.label} active={true}>
                <StepLabel>{step.label}</StepLabel>
                <StepContent>
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                    {step.description}
                  </Typography>
                  <List dense>
                    {step.content.map((item, itemIndex) => (
                      <ListItem key={itemIndex} sx={{ py: 0 }}>
                        <ListItemIcon>
                          <CheckCircleIcon fontSize="small" color="primary" />
                        </ListItemIcon>
                        <ListItemText primary={item} primaryTypographyProps={{ variant: 'body2' }} />
                      </ListItem>
                    ))}
                  </List>
                </StepContent>
              </Step>
            ))}
          </Stepper>
        </AccordionDetails>
      </Accordion>

      {/* Monitoring Setup */}
      <Accordion expanded={expandedSection === 'monitoring'} onChange={handleChange('monitoring')}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <DashboardIcon color="primary" />
            监控设置
          </Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Grid container spacing={3}>
            {monitoringSetup.map((service, index) => (
              <Grid item xs={12} md={6} key={index}>
                <Card variant="outlined">
                  <CardContent>
                    <Typography variant="h6" gutterBottom>
                      {service.service}
                    </Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                      {service.description}
                    </Typography>
                    <List dense>
                      <ListItem sx={{ py: 0 }}>
                        <ListItemText 
                          primary={`端口：${service.port}`} 
                          primaryTypographyProps={{ variant: 'body2' }}
                        />
                      </ListItem>
                      <ListItem sx={{ py: 0 }}>
                        <ListItemText 
                          primary={`配置：${service.config}`} 
                          primaryTypographyProps={{ variant: 'body2' }}
                        />
                      </ListItem>
                    </List>
                    <Chip 
                      label={service.status} 
                      color={service.status.includes('✅') ? 'success' : 'warning'}
                      size="small"
                    />
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </AccordionDetails>
      </Accordion>

      {/* Security Configuration */}
      <Accordion expanded={expandedSection === 'security'} onChange={handleChange('security')}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <SecurityIcon color="primary" />
            安全配置
          </Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Grid container spacing={3}>
            <Grid item xs={12} md={6}>
              <Card variant="outlined">
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    🔐 身份验证
                  </Typography>
                  <List>
                    <ListItem>
                      <ListItemText 
                        primary="JWT 令牌配置" 
                        secondary="设置安全的 JWT 密钥和过期时间"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="OAuth2 集成" 
                        secondary="为 SSO 配置 OAuth2 提供程序"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="基于角色的访问控制" 
                        secondary="配置用户角色和权限"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="API 速率限制" 
                        secondary="为 API 端点实施速率限制"
                      />
                    </ListItem>
                  </List>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} md={6}>
              <Card variant="outlined">
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    🛡️ 网络安全
                  </Typography>
                  <List>
                    <ListItem>
                      <ListItemText 
                        primary="HTTPS 配置" 
                        secondary="为所有通信启用 SSL/TLS"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="防火墙规则" 
                        secondary="为服务访问配置防火墙规则"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="网络策略" 
                        secondary="实施网络策略和防火墙规则"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="密钥管理" 
                        secondary="使用 Docker secrets 或外部密钥管理"
                      />
                    </ListItem>
                  </List>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        </AccordionDetails>
      </Accordion>

      {/* Troubleshooting */}
      <Accordion expanded={expandedSection === 'troubleshooting'} onChange={handleChange('troubleshooting')}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <BugReportIcon color="primary" />
            故障排除
          </Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Grid container spacing={3}>
            <Grid item xs={12} md={6}>
              <Card variant="outlined">
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    🚨 常见问题
                  </Typography>
                  <List>
                    <ListItem>
                      <ListItemText 
                        primary="数据库连接失败" 
                        secondary="检查 PostgreSQL 凭据和网络连接"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="模型服务 API 错误" 
                        secondary="验证 API 密钥和配额限制"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="MCP 工具发现失败" 
                        secondary="检查适配器注册和工具定义"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="内存问题" 
                        secondary="提高容器内存限制或优化查询"
                      />
                    </ListItem>
                  </List>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} md={6}>
              <Card variant="outlined">
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    🔧 调试命令
                  </Typography>
                  <List>
                    <ListItem>
                      <ListItemText 
                        primary="检查服务状态" 
                        secondary="docker compose ps or kubectl get pods"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="查看日志" 
                        secondary="docker compose logs -f or kubectl logs -f"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="健康检查" 
                        secondary="curl http://localhost:8002/api/v1/health"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="数据库检查" 
                        secondary="psql -h localhost -p 5435 -U warehouse_user"
                      />
                    </ListItem>
                  </List>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        </AccordionDetails>
      </Accordion>

      {/* Footer */}
      <Box sx={{ mt: 4, pt: 3, borderTop: 1, borderColor: 'divider' }}>
        <Typography variant="body2" color="text.secondary" align="center">
          部署指南——多智能体智慧仓储系统
        </Typography>
        <Box sx={{ display: 'flex', justifyContent: 'center', gap: 2, mt: 2 }}>
          <Button 
            variant="outlined" 
            startIcon={<GitHubIcon />}
            href="https://github.com/T-DevH/warehouse-operational-assistant"
            target="_blank"
            rel="noopener noreferrer"
          >
            查看源代码
          </Button>
          <Button variant="outlined" startIcon={<DashboardIcon />}>
            在线演示
          </Button>
        </Box>
      </Box>
    </Box>
  );
};

export default DeploymentGuide;

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
  ImageList,
  ImageListItem,
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
  AccountTree as AccountTreeIcon,
  Timeline as TimelineIcon,
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';

const ArchitectureDiagrams: React.FC = () => {
  const navigate = useNavigate();
  const [expandedSection, setExpandedSection] = useState<string | false>('overview');

  const handleChange = (panel: string) => (event: React.SyntheticEvent, isExpanded: boolean) => {
    setExpandedSection(isExpanded ? panel : false);
  };

  const architectureComponents = [
    {
      name: "前端层",
      description: "基于 React 和 Material-UI 组件的用户界面",
      technologies: ["React", "TypeScript", "Material-UI", "React Router"],
      responsibilities: [
        "用户界面渲染",
        "实时聊天界面",
        "仪表板可视化",
        "设备管理 UI",
        "运营监控",
        "安全事件报告"
      ],
      status: "✅ 已完成"
    },
    {
      name: "API 网关",
      description: "基于 FastAPI、具备身份验证与路由能力的 API 网关",
      technologies: ["FastAPI", "Python", "JWT", "OpenAPI"],
      responsibilities: [
        "请求路由与负载均衡",
        "身份验证与授权",
        "API 文档（Swagger）",
        "速率限制与节流",
        "请求/响应验证",
        "错误处理与日志记录"
      ],
      status: "✅ 已完成"
    },
    {
      name: "多智能体系统",
      description: "由 LangGraph 编排、包含专业智能体的多智能体系统",
      technologies: ["LangGraph", "模型服务", "MCP 框架", "Python"],
      responsibilities: [
        "意图分类与路由",
        "智能体编排与协调",
        "工具发现与执行",
        "上下文管理与记忆",
        "响应生成与格式化",
        "错误处理与回退"
      ],
      status: "✅ 已完成"
    },
    {
      name: "专业智能体",
      description: "面向设备、运营和安全领域的专业智能体",
      technologies: ["Python", "MCP 工具", "模型服务", "自定义逻辑"],
      responsibilities: [
        "设备与资产运营",
        "运营协调",
        "安全与合规",
        "工具执行与验证",
        "领域特定推理",
        "行动规划与执行"
      ],
      status: "✅ 已完成"
    },
    {
      name: "MCP 框架",
      description: "用于动态工具发现与执行的模型上下文协议",
      technologies: ["MCP 协议", "Python", "HTTP/WebSocket", "工具注册中心"],
      responsibilities: [
        "动态工具发现",
        "工具绑定与执行",
        "服务发现与注册",
        "工具验证与监控",
        "多服务器通信",
        "资源管理"
      ],
      status: "✅ 已完成"
    },
    {
      name: "推理引擎",
      description: "支持多种推理类型的高级推理能力",
      technologies: ["模型服务", "思维链", "多跳推理", "情景分析"],
      responsibilities: [
        "思维链推理",
        "多跳推理",
        "情景分析",
        "因果推理",
        "模式识别",
        "置信度评分"
      ],
      status: "✅ 已完成"
    },
    {
      name: "数据层",
      description: "采用 PostgreSQL/TimescaleDB 和 Milvus 的混合数据存储",
      technologies: ["PostgreSQL", "TimescaleDB", "Milvus", "Redis", "SQL"],
      responsibilities: [
        "结构化数据存储",
        "时序数据管理",
        "向量相似性搜索",
        "缓存与会话管理",
        "数据迁移与版本管理",
        "备份与恢复"
      ],
      status: "✅ 已完成"
    },
    {
      name: "外部集成",
      description: "面向 WMS、IoT、RFID/条码和考勤系统的适配器",
      technologies: ["REST API", "WebSocket", "数据库连接器", "协议适配器"],
      responsibilities: [
        "WMS 系统集成",
        "IoT 传感器数据收集",
        "RFID/条码扫描",
        "考勤跟踪",
        "ERP 系统集成",
        "第三方 API 管理"
      ],
      status: "🔄 进行中"
    },
    {
      name: "监控栈",
      description: "使用 Prometheus、Grafana 和 Alertmanager 的全面监控",
      technologies: ["Prometheus", "Grafana", "Alertmanager", "Node Exporter"],
      responsibilities: [
        "指标收集与存储",
        "可视化与仪表板",
        "告警路由与通知",
        "性能监控",
        "健康检查与状态",
        "日志聚合与分析"
      ],
      status: "✅ 已完成"
    }
  ];

  const dataFlowSteps = [
    {
      step: 1,
      title: "用户输入",
      description: "用户通过 React 前端发送消息",
      components: ["React UI", "聊天界面", "WebSocket/HTTP"],
      details: "用户在聊天界面中输入消息，前端验证输入并将其发送到 API 网关"
    },
    {
      step: 2,
      title: "API 网关处理",
      description: "FastAPI 网关处理身份验证与路由",
      components: ["FastAPI", "JWT 验证", "速率限制"],
      details: "网关验证 JWT 令牌、应用速率限制，并将请求路由到适当的服务"
    },
    {
      step: 3,
      title: "意图分类",
      description: "模型服务对用户意图进行分类并确定路由",
      components: ["模型服务", "意图分类器", "路由逻辑"],
      details: "LLM 分析用户消息以确定意图（设备、运营或安全）和路由策略"
    },
    {
      step: 4,
      title: "智能体选择",
      description: "LangGraph 选择合适的专业智能体",
      components: ["LangGraph", "智能体路由器", "上下文管理器"],
      details: "系统根据意图分类选择设备、运营或安全智能体"
    },
    {
      step: 5,
      title: "工具发现",
      description: "MCP 框架为任务发现可用工具",
      components: ["MCP 服务端", "工具注册中心", "服务发现"],
      details: "MCP 框架查询工具注册中心，为智能体任务查找相关工具"
    },
    {
      step: 6,
      title: "工具执行",
      description: "使用适当的参数执行所选工具",
      components: ["MCP 客户端", "工具绑定", "执行引擎"],
      details: "工具绑定到执行上下文，并使用经过验证的参数执行"
    },
    {
      step: 7,
      title: "数据检索",
      description: "混合 RAG 系统检索相关数据",
      components: ["PostgreSQL", "Milvus", "向量搜索", "SQL 查询"],
      details: "系统同时查询结构化数据库（PostgreSQL）和向量数据库（Milvus）以获取相关信息"
    },
    {
      step: 8,
      title: "推理分析",
      description: "高级推理引擎处理结果",
      components: ["推理引擎", "思维链", "情景分析"],
      details: "推理引擎应用合适的推理类型来分析检索到的数据并生成洞察"
    },
    {
      step: 9,
      title: "响应生成",
      description: "模型服务生成最终响应",
      components: ["模型服务", "响应格式化器", "结构化数据"],
      details: "LLM 生成包含结构化数据和建议的自然语言响应"
    },
    {
      step: 10,
      title: "响应交付",
      description: "通过 API 网关将响应发回用户",
      components: ["API 网关", "WebSocket/HTTP", "React UI"],
      details: "响应经过格式化后，通过 API 网关返回前端显示"
    }
  ];

  const systemArchitecture = {
    title: "系统架构概览",
    description: "多智能体智慧仓储系统架构的高层视图，展示所有主要组件及其关系",
    components: [
      { name: "前端", type: "UI 层", color: "#1976d2" },
      { name: "API 网关", type: "网关层", color: "#388e3c" },
      { name: "多智能体系统", type: "处理层", color: "#f57c00" },
      { name: "MCP 框架", type: "工具层", color: "#7b1fa2" },
      { name: "数据层", type: "存储层", color: "#d32f2f" },
      { name: "外部系统", type: "集成层", color: "#455a64" },
      { name: "监控", type: "可观测性层", color: "#00796b" }
    ]
  };

  const agentFlowDiagram = {
    title: "智能体流程图",
    description: "展示请求如何通过多智能体系统处理的详细流程",
    flow: [
      "用户输入 → 意图分类 → 智能体选择 → 工具发现 → 工具执行 → 数据检索 → 推理 → 响应生成 → 用户输出"
    ]
  };

  const mcpArchitecture = {
    title: "MCP 框架架构",
    description: "展示工具发现、绑定与执行的模型上下文协议框架",
    components: [
      "MCP 服务端（工具注册）",
      "MCP 客户端（多服务器通信）",
      "工具发现服务（动态注册）",
      "工具绑定服务（智能绑定）",
      "工具路由服务（上下文感知路由）",
      "服务发现注册中心（健康监控）"
    ]
  };

  return (
    <Box sx={{ p: 3, maxWidth: 1200, mx: 'auto' }}>
      {/* Breadcrumbs */}
      <Breadcrumbs sx={{ mb: 2 }}>
        <Button startIcon={<ArrowBackIcon />} onClick={() => navigate('/documentation')}>
          文档
        </Button>
        <Typography color="text.primary">架构图</Typography>
      </Breadcrumbs>

      {/* Header */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h3" component="h1" gutterBottom sx={{ fontWeight: 'bold', color: 'primary.main' }}>
          架构图
        </Typography>
        <Typography variant="h5" component="h2" gutterBottom color="text.secondary">
          系统架构与流程图
        </Typography>
        <Typography variant="body1" sx={{ mb: 2 }}>
          多智能体智慧仓储系统架构的完整可视化文档，
          涵盖系统组件、数据流、智能体交互和 MCP 框架设计。
        </Typography>
        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mb: 3 }}>
          <Chip label="系统架构" color="primary" />
          <Chip label="数据流" color="secondary" />
          <Chip label="智能体交互" color="info" />
          <Chip label="MCP 框架" color="warning" />
          <Chip label="生产就绪" color="success" />
        </Box>
      </Box>

      {/* Status Alert */}
      <Alert severity="success" sx={{ mb: 4 }}>
        <AlertTitle>🏗️ 完整架构文档</AlertTitle>
        系统架构文档已完备，包含所有主要系统组件的详细说明、
        数据流程图和交互模式。
      </Alert>

      {/* System Architecture Overview */}
      <Accordion expanded={expandedSection === 'overview'} onChange={handleChange('overview')}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <ArchitectureIcon color="primary" />
            系统架构概览
          </Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Box sx={{ mb: 3 }}>
            <Typography variant="h5" gutterBottom>
              {systemArchitecture.title}
            </Typography>
            <Typography variant="body1" sx={{ mb: 2 }}>
              {systemArchitecture.description}
            </Typography>
          </Box>

          <Grid container spacing={3}>
            {architectureComponents.map((component, index) => (
              <Grid item xs={12} md={6} key={index}>
                <Card variant="outlined" sx={{ height: '100%' }}>
                  <CardContent>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2 }}>
                      <BuildIcon color="primary" />
                      <Typography variant="h6">{component.name}</Typography>
                    </Box>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                      {component.description}
                    </Typography>
                    <Box sx={{ mb: 2 }}>
                      <Typography variant="subtitle2" gutterBottom>技术：</Typography>
                      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                        {component.technologies.map((tech, techIndex) => (
                          <Chip key={techIndex} label={tech} size="small" variant="outlined" />
                        ))}
                      </Box>
                    </Box>
                    <Box sx={{ mb: 2 }}>
                      <Typography variant="subtitle2" gutterBottom>职责：</Typography>
                      <List dense>
                        {component.responsibilities.map((responsibility, respIndex) => (
                          <ListItem key={respIndex} sx={{ py: 0 }}>
                            <ListItemIcon>
                              <CheckCircleIcon fontSize="small" />
                            </ListItemIcon>
                            <ListItemText primary={responsibility} primaryTypographyProps={{ variant: 'body2' }} />
                          </ListItem>
                        ))}
                      </List>
                    </Box>
                    <Chip 
                      label={component.status} 
                      color={component.status.includes('✅') ? 'success' : 'warning'}
                      size="small"
                    />
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </AccordionDetails>
      </Accordion>

      {/* Data Flow Diagram */}
      <Accordion expanded={expandedSection === 'dataflow'} onChange={handleChange('dataflow')}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <TimelineIcon color="primary" />
            数据流程图
          </Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Box sx={{ mb: 3 }}>
            <Typography variant="h5" gutterBottom>
              请求处理流程
            </Typography>
            <Typography variant="body1" sx={{ mb: 2 }}>
              展示用户请求如何在整个系统中处理的详细分步流程，
              从前端输入一直到响应交付。
            </Typography>
          </Box>

          <Grid container spacing={2}>
            {dataFlowSteps.map((step, index) => (
              <Grid item xs={12} md={6} key={index}>
                <Card variant="outlined">
                  <CardContent>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2 }}>
                      <Chip label={`步骤 ${step.step}`} color="primary" />
                      <Typography variant="h6">{step.title}</Typography>
                    </Box>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                      {step.description}
                    </Typography>
                    <Box sx={{ mb: 2 }}>
                      <Typography variant="subtitle2" gutterBottom>组件：</Typography>
                      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                        {step.components.map((component, compIndex) => (
                          <Chip key={compIndex} label={component} size="small" variant="outlined" />
                        ))}
                      </Box>
                    </Box>
                    <Typography variant="body2" sx={{ fontStyle: 'italic' }}>
                      {step.details}
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </AccordionDetails>
      </Accordion>

      {/* Agent Flow Diagram */}
      <Accordion expanded={expandedSection === 'agentflow'} onChange={handleChange('agentflow')}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <AccountTreeIcon color="primary" />
            智能体流程图
          </Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Box sx={{ mb: 3 }}>
            <Typography variant="h5" gutterBottom>
              {agentFlowDiagram.title}
            </Typography>
            <Typography variant="body1" sx={{ mb: 2 }}>
              {agentFlowDiagram.description}
            </Typography>
          </Box>

          <Card variant="outlined">
            <CardContent>
              <Typography variant="h6" gutterBottom>
                多智能体处理流程
              </Typography>
              <Paper sx={{ p: 3, bgcolor: 'grey.50', textAlign: 'center' }}>
                <Typography variant="body1" sx={{ fontFamily: 'monospace', fontSize: '1.1rem' }}>
                  {agentFlowDiagram.flow[0]}
                </Typography>
              </Paper>
            </CardContent>
          </Card>

          <Grid container spacing={3} sx={{ mt: 2 }}>
            <Grid item xs={12} md={4}>
              <Card variant="outlined">
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    设备智能体
                  </Typography>
                  <List dense>
                    <ListItem sx={{ py: 0 }}>
                      <ListItemText primary="设备查询与状态" primaryTypographyProps={{ variant: 'body2' }} />
                    </ListItem>
                    <ListItem sx={{ py: 0 }}>
                      <ListItemText primary="设备调度与分配" primaryTypographyProps={{ variant: 'body2' }} />
                    </ListItem>
                    <ListItem sx={{ py: 0 }}>
                      <ListItemText primary="维护计划" primaryTypographyProps={{ variant: 'body2' }} />
                    </ListItem>
                    <ListItem sx={{ py: 0 }}>
                      <ListItemText primary="可用性检查" primaryTypographyProps={{ variant: 'body2' }} />
                    </ListItem>
                  </List>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} md={4}>
              <Card variant="outlined">
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    运营智能体
                  </Typography>
                  <List dense>
                    <ListItem sx={{ py: 0 }}>
                      <ListItemText primary="创建拣货波次" primaryTypographyProps={{ variant: 'body2' }} />
                    </ListItem>
                    <ListItem sx={{ py: 0 }}>
                      <ListItemText primary="任务分配" primaryTypographyProps={{ variant: 'body2' }} />
                    </ListItem>
                    <ListItem sx={{ py: 0 }}>
                      <ListItemText primary="工作流优化" primaryTypographyProps={{ variant: 'body2' }} />
                    </ListItem>
                    <ListItem sx={{ py: 0 }}>
                      <ListItemText primary="性能监控" primaryTypographyProps={{ variant: 'body2' }} />
                    </ListItem>
                  </List>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} md={4}>
              <Card variant="outlined">
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    安全智能体
                  </Typography>
                  <List dense>
                    <ListItem sx={{ py: 0 }}>
                      <ListItemText primary="事件报告" primaryTypographyProps={{ variant: 'body2' }} />
                    </ListItem>
                    <ListItem sx={{ py: 0 }}>
                      <ListItemText primary="安全合规" primaryTypographyProps={{ variant: 'body2' }} />
                    </ListItem>
                    <ListItem sx={{ py: 0 }}>
                      <ListItemText primary="风险评估" primaryTypographyProps={{ variant: 'body2' }} />
                    </ListItem>
                    <ListItem sx={{ py: 0 }}>
                      <ListItemText primary="培训管理" primaryTypographyProps={{ variant: 'body2' }} />
                    </ListItem>
                  </List>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        </AccordionDetails>
      </Accordion>

      {/* MCP Architecture */}
      <Accordion expanded={expandedSection === 'mcp'} onChange={handleChange('mcp')}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <BuildIcon color="primary" />
            MCP 框架架构
          </Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Box sx={{ mb: 3 }}>
            <Typography variant="h5" gutterBottom>
              {mcpArchitecture.title}
            </Typography>
            <Typography variant="body1" sx={{ mb: 2 }}>
              {mcpArchitecture.description}
            </Typography>
          </Box>

          <Grid container spacing={3}>
            {mcpArchitecture.components.map((component, index) => (
              <Grid item xs={12} md={6} key={index}>
                <Card variant="outlined">
                  <CardContent>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2 }}>
                      <Chip label={index + 1} color="primary" />
                      <Typography variant="h6">{component}</Typography>
                    </Box>
                    <Typography variant="body2" color="text.secondary">
                      MCP 框架的核心组件，为工具管理与执行提供关键功能。
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </AccordionDetails>
      </Accordion>

      {/* Technology Stack */}
      <Accordion expanded={expandedSection === 'techstack'} onChange={handleChange('techstack')}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <CodeIcon color="primary" />
            技术栈
          </Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Grid container spacing={3}>
            <Grid item xs={12} md={6}>
              <Card variant="outlined">
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    前端技术
                  </Typography>
                  <List dense>
                    <ListItem>
                      <ListItemText 
                        primary="React 18" 
                        secondary="采用 hooks 和并发特性的现代 React"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="TypeScript" 
                        secondary="类型安全的 JavaScript 开发"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="Material-UI" 
                        secondary="Google Material Design 组件"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="React Router" 
                        secondary="客户端路由与导航"
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
                    后端技术
                  </Typography>
                  <List dense>
                    <ListItem>
                      <ListItemText 
                        primary="FastAPI" 
                        secondary="自动生成 API 文档的现代 Python Web 框架"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="LangGraph" 
                        secondary="多智能体编排与工作流管理"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="模型服务" 
                        secondary="Llama 3.3 Nemotron Super 49B + NV-EmbedQA-E5-v5 嵌入模型"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="MCP 框架" 
                        secondary="用于工具发现与执行的模型上下文协议"
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
                    数据技术
                  </Typography>
                  <List dense>
                    <ListItem>
                      <ListItemText 
                        primary="PostgreSQL" 
                        secondary="用于结构化数据的主关系数据库"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="TimescaleDB" 
                        secondary="用于遥测的时序数据扩展"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="Milvus" 
                        secondary="用于语义搜索的向量数据库"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="Redis" 
                        secondary="内存缓存与会话存储"
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
                    基础设施技术
                  </Typography>
                  <List dense>
                    <ListItem>
                      <ListItemText 
                        primary="Docker" 
                        secondary="用于一致部署的容器化技术"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="Kubernetes" 
                        secondary="用于生产环境的容器编排"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="Prometheus" 
                        secondary="指标收集与监控"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="Grafana" 
                        secondary="可视化与仪表板"
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
          架构图——多智能体智慧仓储系统
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

export default ArchitectureDiagrams;

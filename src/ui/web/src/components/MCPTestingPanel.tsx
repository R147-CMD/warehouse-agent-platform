import React, { useState, useEffect } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Button,
  TextField,
  Chip,
  List,
  ListItem,
  ListItemText,
  ListItemSecondaryAction,
  IconButton,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Alert,
  CircularProgress,
  Grid,
  Paper,
  Divider,
} from '@mui/material';
import {
  ExpandMore as ExpandMoreIcon,
  PlayArrow as PlayIcon,
  Refresh as RefreshIcon,
  Search as SearchIcon,
  CheckCircle as CheckCircleIcon,
} from '@mui/icons-material';
import { mcpAPI } from '../services/api';
import { translateMcpCategory, translateMcpDescription } from '../localization/zhCN';

interface MCPTool {
  tool_id: string;
  name: string;
  description: string;
  category: string;
  source: string;
  capabilities: string[];
  metadata: any;
  relevance_score?: number;
}

interface MCPStatus {
  status: string;
  tool_discovery: {
    discovered_tools: number;
    discovery_sources: number;
    is_running: boolean;
  };
  services: {
    tool_discovery: string;
    tool_binding: string;
    tool_routing: string;
    tool_validation: string;
  };
}

const MCPTestingPanel: React.FC = () => {
  const [mcpStatus, setMcpStatus] = useState<MCPStatus | null>(null);
  const [tools, setTools] = useState<MCPTool[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<MCPTool[]>([]);
  const [testMessage, setTestMessage] = useState('');
  const [testResult, setTestResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [refreshLoading, setRefreshLoading] = useState(false);

  // Load MCP status and tools on component mount
  useEffect(() => {
    loadMcpData();
  }, []);

  const loadMcpData = async () => {
    try {
      setLoading(true);
      setError(null);
      setSuccess(null);
      
      // Load MCP status
      const status = await mcpAPI.getStatus();
      setMcpStatus(status);
      
      // Load discovered tools
      const toolsData = await mcpAPI.getTools();
      setTools(toolsData.tools || []);
      
      if (toolsData.tools && toolsData.tools.length > 0) {
        setSuccess(`已成功加载 ${toolsData.tools.length} 个 MCP 工具`);
      } else {
        setError('未发现 MCP 工具，请尝试刷新发现结果。');
      }
      
    } catch {
      setError('MCP 数据加载失败，请检查服务连接后重试。');
    } finally {
      setLoading(false);
    }
  };

  const handleRefreshDiscovery = async () => {
    try {
      setRefreshLoading(true);
      setError(null);
      setSuccess(null);
      
      const result = await mcpAPI.refreshDiscovery();
      setSuccess(`发现结果已刷新：找到 ${result.total_tools} 个工具`);
      
      // Reload data after refresh
      await loadMcpData();
      
    } catch {
      setError('刷新发现结果失败，请稍后重试。');
    } finally {
      setRefreshLoading(false);
    }
  };

  const handleSearchTools = async () => {
    if (!searchQuery.trim()) return;
    
    try {
      setLoading(true);
      setError(null);
      setSuccess(null);
      
      const results = await mcpAPI.searchTools(searchQuery);
      setSearchResults(results.tools || []);
      
      if (results.tools && results.tools.length > 0) {
        setSuccess(`找到 ${results.tools.length} 个与“${searchQuery}”匹配的工具`);
      } else {
        setError(`未找到与“${searchQuery}”匹配的工具，请尝试其他搜索词。`);
      }
      
    } catch {
      setError('搜索失败，请检查服务连接后重试。');
    } finally {
      setLoading(false);
    }
  };

  const handleTestWorkflow = async () => {
    if (!testMessage.trim()) return;
    
    try {
      setLoading(true);
      setError(null);
      setSuccess(null);
      
      const result = await mcpAPI.testWorkflow(testMessage);
      setTestResult(result);
      
      if (result.status === 'success') {
        setSuccess('工作流测试成功完成');
      } else {
        setError('工作流测试失败，请检查测试消息或服务状态。');
      }
      
    } catch {
      setError('工作流测试失败，请检查服务连接后重试。');
    } finally {
      setLoading(false);
    }
  };

  const handleExecuteTool = async (toolId: string) => {
    try {
      setLoading(true);
      setError(null);
      
      const result = await mcpAPI.executeTool(toolId, { test: true });
      console.log(`Tool ${toolId} executed:`, result);
      
      // Show success message
      setError(`工具 ${toolId} 已成功执行！`);
      
    } catch {
      setError('工具执行失败，请检查参数或服务状态。');
    } finally {
      setLoading(false);
    }
  };

  const getStatusLabel = (status: unknown) => {
    const normalizedStatus = String(status);
    const labels: Record<string, string> = {
      operational: '运行正常',
      connected: '已连接',
      disconnected: '未连接',
      running: '运行中',
      stopped: '已停止',
      error: '错误',
    };
    return labels[normalizedStatus] || normalizedStatus;
  };

  const getServiceLabel = (service: string) => {
    const labels: Record<string, string> = {
      tool_discovery: '工具发现',
      tool_binding: '工具绑定',
      tool_routing: '工具路由',
      tool_validation: '工具验证',
    };
    return labels[service] || service.replace('_', ' ').toUpperCase();
  };

  return (
    <Box sx={{ p: 2 }}>
      <Typography variant="h5" gutterBottom>
        MCP 测试面板
      </Typography>
      
      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {success && (
        <Alert severity="success" sx={{ mb: 2 }} onClose={() => setSuccess(null)}>
          {success}
        </Alert>
      )}

      <Grid container spacing={2}>
        {/* MCP Status */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                MCP 框架状态
              </Typography>
              
              {mcpStatus ? (
                <Box>
                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                    <CheckCircleIcon color="success" sx={{ mr: 1 }} />
                    <Typography variant="body1">
                      状态：<strong>{getStatusLabel(mcpStatus.status)}</strong>
                    </Typography>
                  </Box>
                  
                  <Typography variant="body2" gutterBottom>
                    <strong>工具发现：</strong>
                  </Typography>
                  <Typography variant="body2" sx={{ ml: 2 }}>
                    • 已发现工具：{mcpStatus.tool_discovery.discovered_tools}
                  </Typography>
                  <Typography variant="body2" sx={{ ml: 2 }}>
                    • 发现来源：{mcpStatus.tool_discovery.discovery_sources}
                  </Typography>
                  <Typography variant="body2" sx={{ ml: 2 }}>
                    • 运行中：{mcpStatus.tool_discovery.is_running ? '是' : '否'}
                  </Typography>
                  
                  <Divider sx={{ my: 2 }} />
                  
                  <Typography variant="body2" gutterBottom>
                    <strong>服务：</strong>
                  </Typography>
                  {Object.entries(mcpStatus.services).map(([service, status]) => (
                    <Box key={service} sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                      <Chip 
                        label={getStatusLabel(status)} 
                        color={status === 'operational' ? 'success' : 'error'}
                        size="small"
                        sx={{ mr: 1 }}
                      />
                      <Typography variant="body2">
                        {getServiceLabel(service)}
                      </Typography>
                    </Box>
                  ))}
                  
                  <Button
                    variant="outlined"
                    startIcon={refreshLoading ? <CircularProgress size={16} /> : <RefreshIcon />}
                    onClick={handleRefreshDiscovery}
                    disabled={refreshLoading || loading}
                    sx={{ mt: 2 }}
                  >
                    {refreshLoading ? '正在刷新...' : '刷新发现结果'}
                  </Button>
                </Box>
              ) : (
                <CircularProgress />
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Tool Search */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                工具搜索
              </Typography>
              
              <Box sx={{ display: 'flex', gap: 1, mb: 2 }}>
                <TextField
                  fullWidth
                  label="搜索工具..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && handleSearchTools()}
                />
                <Button
                  variant="contained"
                  startIcon={<SearchIcon />}
                  onClick={handleSearchTools}
                  disabled={loading || !searchQuery.trim()}
                >
                  搜索
                </Button>
              </Box>
              
              {searchResults.length > 0 && (
                <Box>
                  <Typography variant="body2" gutterBottom>
                    找到 {searchResults.length} 个工具：
                  </Typography>
                  <List dense>
                    {searchResults.map((tool) => (
                      <ListItem key={tool.tool_id}>
                        <ListItemText
                          primary={tool.name}
                          secondary={`${translateMcpDescription(tool.description, tool.name)}（${translateMcpCategory(tool.category)}）`}
                        />
                        <ListItemSecondaryAction>
                          <IconButton
                            edge="end"
                            onClick={() => handleExecuteTool(tool.tool_id)}
                            disabled={loading}
                          >
                            <PlayIcon />
                          </IconButton>
                        </ListItemSecondaryAction>
                      </ListItem>
                    ))}
                  </List>
                </Box>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Discovered Tools */}
        <Grid item xs={12}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                 已发现工具（{tools.length}）
              </Typography>
              
              {tools.length > 0 ? (
                <Accordion>
                  <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                    <Typography>查看全部工具</Typography>
                  </AccordionSummary>
                  <AccordionDetails>
                    <List dense>
                      {tools.map((tool) => (
                        <ListItem key={tool.tool_id}>
                          <ListItemText
                            primary={tool.name}
                            secondary={
                              <Box>
                                <Typography variant="body2" color="text.secondary">
                                  {translateMcpDescription(tool.description, tool.name)}
                                </Typography>
                                <Box sx={{ mt: 1 }}>
                                  <Chip label={translateMcpCategory(tool.category)} size="small" sx={{ mr: 1 }} />
                                  <Chip label={tool.source} size="small" />
                                </Box>
                              </Box>
                            }
                          />
                          <ListItemSecondaryAction>
                            <IconButton
                              edge="end"
                              onClick={() => handleExecuteTool(tool.tool_id)}
                              disabled={loading}
                            >
                              <PlayIcon />
                            </IconButton>
                          </ListItemSecondaryAction>
                        </ListItem>
                      ))}
                    </List>
                  </AccordionDetails>
                </Accordion>
              ) : (
                <Typography variant="body2" color="text.secondary">
                  尚未发现工具，请尝试刷新发现结果。
                </Typography>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Workflow Testing */}
        <Grid item xs={12}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                MCP 工作流测试
              </Typography>
              
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                使用示例消息测试完整的 MCP 工作流：
              </Typography>
              
              <Box sx={{ display: 'flex', gap: 1, mb: 2, flexWrap: 'wrap' }}>
                <Button
                  variant="outlined"
                  size="small"
                  onClick={() => setTestMessage('显示叉车 FL-001 的状态。')}
                >
                  设备状态
                </Button>
                <Button
                  variant="outlined"
                  size="small"
                  onClick={() => setTestMessage('为订单 ORD-123 创建新的拣货任务。')}
                >
                  创建任务
                </Button>
                <Button
                  variant="outlined"
                  size="small"
                  onClick={() => setTestMessage('报告 A 区发生的一起安全事件。')}
                >
                  安全报告
                </Button>
                <Button
                  variant="outlined"
                  size="small"
                  onClick={() => setTestMessage('当前有哪些设备可用？')}
                >
                  可用设备
                </Button>
              </Box>
              
              <Box sx={{ display: 'flex', gap: 1, mb: 2 }}>
                <TextField
                  fullWidth
                  label="测试消息..."
                  value={testMessage}
                  onChange={(e) => setTestMessage(e.target.value)}
                  placeholder="例如：显示叉车 FL-001 的状态"
                />
                <Button
                  variant="contained"
                  startIcon={loading ? <CircularProgress size={16} /> : <PlayIcon />}
                  onClick={handleTestWorkflow}
                  disabled={loading || !testMessage.trim()}
                >
                  {loading ? '正在测试...' : '测试工作流'}
                </Button>
              </Box>
              
              {testResult && (
                <Paper sx={{ p: 2, bgcolor: 'grey.50' }}>
                  <Typography variant="subtitle2" gutterBottom>
                    工作流测试结果：
                  </Typography>
                  <Typography variant="body2" component="pre" sx={{ whiteSpace: 'pre-wrap' }}>
                    {JSON.stringify(testResult, null, 2)}
                  </Typography>
                </Paper>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
};

export default MCPTestingPanel;

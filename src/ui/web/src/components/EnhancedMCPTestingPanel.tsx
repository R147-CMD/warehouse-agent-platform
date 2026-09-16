import React, { useState, useEffect, useCallback, useMemo } from 'react';
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
  Tabs,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Badge,
  Tooltip,
  LinearProgress,
  Collapse,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  MenuItem,
  Select,
  FormControl,
  InputLabel,
  Checkbox,
  FormControlLabel,
  Switch,
  SelectChangeEvent,
  Autocomplete,
  Stack,
  Skeleton,
  Fab,
} from '@mui/material';
import {
  ExpandMore as ExpandMoreIcon,
  PlayArrow as PlayIcon,
  Refresh as RefreshIcon,
  Search as SearchIcon,
  CheckCircle as CheckCircleIcon,
  Error as ErrorIcon,
  Info as InfoIcon,
  History as HistoryIcon,
  Speed as SpeedIcon,
  Assessment as AssessmentIcon,
  Code as CodeIcon,
  Visibility as VisibilityIcon,
  ContentCopy as CopyIcon,
  Download as DownloadIcon,
  Delete as DeleteIcon,
  Save as SaveIcon,
  Upload as UploadIcon,
  CompareArrows as CompareIcon,
  FilterList as FilterIcon,
  Clear as ClearIcon,
  Replay as RetryIcon,
  Wifi as WifiIcon,
  WifiOff as WifiOffIcon,
} from '@mui/icons-material';
import CopyToClipboard from 'react-copy-to-clipboard';
import JsonView from '@uiw/react-json-view';
import { LineChart, Line, BarChart, Bar, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, Legend, ResponsiveContainer } from 'recharts';
import { format as formatDate, subDays, parseISO } from 'date-fns';
import Papa from 'papaparse';
import { mcpAPI } from '../services/api';
import { useSearchParams } from 'react-router-dom';
import {
  translateMcpCapability,
  translateMcpAgentNote,
  translateMcpCategory,
  translateMcpDescription,
  translateMcpParameterDescription,
} from '../localization/zhCN';

interface MCPTool {
  tool_id: string;
  name: string;
  description: string;
  category: string;
  source: string;
  capabilities: string[];
  metadata: any;
  parameters?: any;
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

interface ExecutionHistory {
  id: string;
  timestamp: Date;
  tool_id: string;
  tool_name: string;
  success: boolean;
  execution_time: number;
  result: any;
  error?: string;
  errorType?: 'network' | 'validation' | 'execution' | 'timeout';
  parameters?: any;
}

interface ErrorDetails {
  type: 'network' | 'validation' | 'execution' | 'timeout';
  message: string;
  details?: any;
  timestamp: Date;
  retryable: boolean;
}

interface TestScenario {
  id: string;
  name: string;
  message: string;
  description?: string;
  tags?: string[];
  created: Date;
  lastUsed?: Date;
}

interface ToolFilters {
  category: string;
  source: string;
  search: string;
  status?: 'all' | 'success' | 'failed';
}

interface HistoryFilters {
  tool: string;
  status: 'all' | 'success' | 'failed';
  dateRange: 'all' | 'today' | 'week' | 'month';
  search: string;
}

interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

function TabPanel(props: TabPanelProps) {
  const { children, value, index, ...other } = props;
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`mcp-tabpanel-${index}`}
      aria-labelledby={`mcp-tab-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ p: 3 }}>{children}</Box>}
    </div>
  );
}

const EnhancedMCPTestingPanel: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  
  // Core state
  const [mcpStatus, setMcpStatus] = useState<MCPStatus | null>(null);
  const [tools, setTools] = useState<MCPTool[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<MCPTool[]>([]);
  const [testMessage, setTestMessage] = useState('');
  const [testResult, setTestResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ErrorDetails | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [refreshLoading, setRefreshLoading] = useState(false);
  const [tabValue, setTabValue] = useState(parseInt(searchParams.get('tab') || '0'));
  const [executionHistory, setExecutionHistory] = useState<ExecutionHistory[]>([]);
  const [showToolDetails, setShowToolDetails] = useState<string | null>(null);
  const [toolParameters, setToolParameters] = useState<{ [key: string]: any }>({});
  const [parameterErrors, setParameterErrors] = useState<{ [key: string]: string }>({});
  const [selectedToolForExecution, setSelectedToolForExecution] = useState<MCPTool | null>(null);
  const [showParameterDialog, setShowParameterDialog] = useState(false);
  const [agentsStatus, setAgentsStatus] = useState<any>(null);
  const [selectedHistoryEntry, setSelectedHistoryEntry] = useState<ExecutionHistory | null>(null);
  const [selectedHistoryEntries, setSelectedHistoryEntries] = useState<string[]>([]);
  const [showComparisonDialog, setShowComparisonDialog] = useState(false);
  // Real-time updates
  const [lastUpdateTime, setLastUpdateTime] = useState<Date>(new Date());
  const [connectionStatus, setConnectionStatus] = useState<'connected' | 'disconnected' | 'checking'>('checking');
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [dataStale, setDataStale] = useState(false);
  
  // Filters and sorting
  const [toolFilters, setToolFilters] = useState<ToolFilters>({
    category: '',
    source: '',
    search: '',
  });
  const [historyFilters, setHistoryFilters] = useState<HistoryFilters>({
    tool: '',
    status: 'all',
    dateRange: 'all',
    search: '',
  });
  const [toolSortBy, setToolSortBy] = useState<'name' | 'category' | 'source'>('name');
  const [showFilters, setShowFilters] = useState(false);
  
  // Test scenarios
  const [testScenarios, setTestScenarios] = useState<TestScenario[]>([]);
  const [showScenarioDialog, setShowScenarioDialog] = useState(false);
  const [selectedScenario, setSelectedScenario] = useState<Partial<TestScenario>>({ name: '', description: '', message: testMessage });
  
  // Bulk operations
  const [selectedTools, setSelectedTools] = useState<string[]>([]);
  const [bulkExecuting, setBulkExecuting] = useState(false);
  
  // Performance metrics
  const [performanceMetrics, setPerformanceMetrics] = useState({
    totalExecutions: 0,
    successRate: 0,
    averageExecutionTime: 0,
    lastExecutionTime: 0
  });

  // Load initial data
  useEffect(() => {
    loadMcpData();
    loadExecutionHistory();
    loadAgentsStatus();
    loadTestScenarios();
    
    // Load test message from URL
    const urlMessage = searchParams.get('message');
    if (urlMessage) {
      setTestMessage(decodeURIComponent(urlMessage));
    }
  }, []);

  // Real-time status updates
  useEffect(() => {
    if (!autoRefresh) return;
    
    const interval = setInterval(() => {
      loadMcpData(true); // Silent refresh
      checkConnectionStatus();
    }, 30000); // 30 seconds
    
    return () => clearInterval(interval);
  }, [autoRefresh]);

  // Check data staleness
  useEffect(() => {
    const checkStaleness = setInterval(() => {
      const now = new Date();
      const timeSinceUpdate = now.getTime() - lastUpdateTime.getTime();
      setDataStale(timeSinceUpdate > 60000); // Stale after 1 minute
    }, 5000);
    
    return () => clearInterval(checkStaleness);
  }, [lastUpdateTime]);

  // Update URL when tab changes
  useEffect(() => {
    const newParams = new URLSearchParams(searchParams);
    newParams.set('tab', tabValue.toString());
    setSearchParams(newParams, { replace: true });
  }, [tabValue]);

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyPress = (e: KeyboardEvent) => {
      // Ctrl/Cmd + Enter to execute
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        if (tabValue === 2 && testMessage) {
          e.preventDefault();
          handleTestWorkflow();
        }
      }
      // Ctrl/Cmd + K to focus search
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        if (tabValue === 1) {
          const searchInput = document.querySelector('input[placeholder*="Ctrl/Cmd"]') as HTMLInputElement;
          searchInput?.focus();
        }
      }
      // Ctrl/Cmd + R to refresh (prevent default browser refresh)
      if ((e.ctrlKey || e.metaKey) && e.key === 'r' && (tabValue === 0 || tabValue === 1)) {
        e.preventDefault();
        handleRefreshDiscovery();
      }
      // Esc to close dialogs
      if (e.key === 'Escape') {
        setShowParameterDialog(false);
        setSelectedHistoryEntry(null);
        setShowComparisonDialog(false);
        setShowScenarioDialog(false);
      }
    };
    
    window.addEventListener('keydown', handleKeyPress);
    return () => window.removeEventListener('keydown', handleKeyPress);
  }, [tabValue, testMessage]);

  const checkConnectionStatus = async () => {
    try {
      await mcpAPI.getStatus();
      setConnectionStatus('connected');
    } catch {
      setConnectionStatus('disconnected');
    }
  };

  const loadAgentsStatus = async () => {
    try {
      const status = await mcpAPI.getAgents();
      setAgentsStatus(status);
    } catch (err: any) {
      console.warn(`Failed to load agents status: ${err.message}`);
    }
  };

  const loadMcpData = async (silent = false) => {
    try {
      if (!silent) setLoading(true);
      setError(null);
      if (!silent) setSuccess(null);
      
      const status = await mcpAPI.getStatus();
      setMcpStatus(status);
      setConnectionStatus('connected');
      
      const toolsData = await mcpAPI.getTools();
      setTools(toolsData.tools || []);
      setLastUpdateTime(new Date());
      setDataStale(false);
      
      if (!silent) {
        if (toolsData.tools && toolsData.tools.length > 0) {
          setSuccess(`已成功加载 ${toolsData.tools.length} 个 MCP 工具`);
        } else {
          setError({
            type: 'execution',
            message: '未发现 MCP 工具，请尝试刷新发现结果。',
            timestamp: new Date(),
            retryable: true,
          });
        }
      }
    } catch (err: any) {
      const errorDetails: ErrorDetails = {
        type: 'network',
        message: 'MCP 数据加载失败，请检查服务连接后重试。',
        timestamp: new Date(),
        retryable: true,
        details: err.response?.data,
      };
      setError(errorDetails);
      setConnectionStatus('disconnected');
    } finally {
      if (!silent) setLoading(false);
    }
  };

  const loadExecutionHistory = () => {
    try {
      const history = JSON.parse(localStorage.getItem('mcp_execution_history') || '[]');
      // Convert timestamp strings back to Date objects
      const parsedHistory = history.map((entry: any) => ({
        ...entry,
        timestamp: new Date(entry.timestamp),
      }));
      setExecutionHistory(parsedHistory);
      updatePerformanceMetrics(parsedHistory);
    } catch (err) {
      console.error('Failed to load execution history:', err);
    }
  };

  const loadTestScenarios = () => {
    try {
      const scenarios = JSON.parse(localStorage.getItem('mcp_test_scenarios') || '[]');
      const parsedScenarios = scenarios.map((s: any) => ({
        ...s,
        created: new Date(s.created),
        lastUsed: s.lastUsed ? new Date(s.lastUsed) : undefined,
      }));
      setTestScenarios(parsedScenarios);
    } catch (err) {
      console.error('Failed to load test scenarios:', err);
    }
  };

  const saveTestScenario = (scenario: Omit<TestScenario, 'id' | 'created'>) => {
    const newScenario: TestScenario = {
      ...scenario,
      id: Date.now().toString(),
      created: new Date(),
    };
    const updated = [newScenario, ...testScenarios];
    setTestScenarios(updated);
    localStorage.setItem('mcp_test_scenarios', JSON.stringify(updated));
    setShowScenarioDialog(false);
    setSuccess('测试场景已成功保存');
  };

  const loadTestScenario = (scenario: TestScenario) => {
    setTestMessage(scenario.message);
    setTabValue(2);
    const updated = testScenarios.map(s => 
      s.id === scenario.id ? { ...s, lastUsed: new Date() } : s
    );
    setTestScenarios(updated);
    localStorage.setItem('mcp_test_scenarios', JSON.stringify(updated));
  };

  const shareScenario = (scenario: TestScenario) => {
    const url = new URL(window.location.href);
    url.searchParams.set('message', scenario.message);
    url.searchParams.set('tab', '2');
    navigator.clipboard.writeText(url.toString());
    setSuccess('场景 URL 已复制到剪贴板！');
  };

  const updatePerformanceMetrics = (history: ExecutionHistory[]) => {
    if (history.length === 0) {
      setPerformanceMetrics({
        totalExecutions: 0,
        successRate: 0,
        averageExecutionTime: 0,
        lastExecutionTime: 0
      });
      return;
    }
    
    const totalExecutions = history.length;
    const successfulExecutions = history.filter(h => h.success).length;
    const successRate = (successfulExecutions / totalExecutions) * 100;
    const averageExecutionTime = history.reduce((sum, h) => sum + h.execution_time, 0) / totalExecutions;
    const lastExecutionTime = history[history.length - 1]?.execution_time || 0;
    
    setPerformanceMetrics({
      totalExecutions,
      successRate,
      averageExecutionTime,
      lastExecutionTime
    });
  };

  const handleRefreshDiscovery = async () => {
    try {
      setRefreshLoading(true);
      setError(null);
      setSuccess(null);
      
      const result = await mcpAPI.refreshDiscovery();
      setSuccess(`发现结果已刷新：找到 ${result.total_tools} 个工具`);
      
      await loadMcpData();
      
    } catch (err: any) {
      setError({
        type: 'network',
        message: '刷新发现结果失败，请稍后重试。',
        timestamp: new Date(),
        retryable: true,
        details: err.response?.data,
      });
    } finally {
      setRefreshLoading(false);
    }
  };

  const handleRetry = useCallback(() => {
    if (error?.retryable) {
      if (error.type === 'network') {
        loadMcpData();
      } else if (error.type === 'execution') {
        handleRefreshDiscovery();
      }
    }
  }, [error]);

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
        setError({
          type: 'execution',
          message: `未找到与“${searchQuery}”匹配的工具，请尝试其他搜索词。`,
          timestamp: new Date(),
          retryable: false,
        });
      }
      
    } catch (err: any) {
      setError({
        type: 'network',
        message: '搜索失败，请检查服务连接后重试。',
        timestamp: new Date(),
        retryable: true,
        details: err.response?.data,
      });
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
      
      const startTime = Date.now();
      const result = await mcpAPI.testWorkflow(testMessage);
      const executionTime = Date.now() - startTime;
      
      setTestResult(result);
      
      const historyEntry: ExecutionHistory = {
        id: Date.now().toString(),
        timestamp: new Date(),
        tool_id: 'workflow_test',
        tool_name: 'MCP 工作流测试',
        success: result.status === 'success',
        execution_time: executionTime,
        result: result,
        error: result.status !== 'success' ? result.error : undefined,
        errorType: result.status !== 'success' ? 'execution' : undefined,
      };
      
      const newHistory = [historyEntry, ...executionHistory.slice(0, 99)]; // Keep last 100
      setExecutionHistory(newHistory);
      localStorage.setItem('mcp_execution_history', JSON.stringify(newHistory));
      updatePerformanceMetrics(newHistory);
      
      if (result.status === 'success') {
        setSuccess(`工作流测试成功完成，耗时 ${executionTime}ms`);
      } else {
        setError({
          type: 'execution',
          message: '工作流测试失败，请检查测试消息或服务状态。',
          timestamp: new Date(),
          retryable: false,
          details: result,
        });
      }
      
    } catch (err: any) {
      const errorDetails: ErrorDetails = {
        type: err.code === 'ECONNABORTED' ? 'timeout' : 'network',
        message: '工作流测试失败，请检查服务连接后重试。',
        timestamp: new Date(),
        retryable: true,
        details: err.response?.data,
      };
      setError(errorDetails);
    } finally {
      setLoading(false);
    }
  };

  const validateParameters = (tool: MCPTool, params: any): string | null => {
    if (!tool.parameters || typeof tool.parameters !== 'object') return null;
    
    try {
      // Basic validation - check required fields
      const schema = tool.parameters;
      if (schema.required && Array.isArray(schema.required)) {
        for (const field of schema.required) {
          if (params[field] === undefined || params[field] === null || params[field] === '') {
            return `缺少必填参数“${field}”`;
          }
        }
      }
      
      // Type validation
      if (schema.properties) {
        for (const [key, value] of Object.entries(params)) {
          const prop = (schema.properties as any)[key];
          if (prop) {
            if (prop.type === 'number' && isNaN(Number(value))) {
              return `参数“${key}”必须是数字`;
            }
            if (prop.type === 'boolean' && typeof value !== 'boolean') {
              return `参数“${key}”必须是布尔值`;
            }
            if (prop.type === 'array' && !Array.isArray(value)) {
              return `参数“${key}”必须是数组`;
            }
          }
        }
      }
      
      return null;
    } catch (err) {
      return '参数格式无效';
    }
  };

  const handleExecuteTool = async (toolId: string, toolName: string, parameters?: any) => {
    const tool = tools.find(t => t.tool_id === toolId);
    if (tool && parameters) {
      const validationError = validateParameters(tool, parameters);
      if (validationError) {
        setError({
          type: 'validation',
          message: validationError,
          timestamp: new Date(),
          retryable: false,
        });
        setParameterErrors({ [toolId]: validationError });
        return;
      }
    }
    
    try {
      setLoading(true);
      setError(null);
      setParameterErrors({});
      
      const startTime = Date.now();
      const execParams = parameters || toolParameters[toolId] || { test: true };
      const result = await mcpAPI.executeTool(toolId, execParams);
      const executionTime = Date.now() - startTime;
      
      const historyEntry: ExecutionHistory = {
        id: Date.now().toString(),
        timestamp: new Date(),
        tool_id: toolId,
        tool_name: toolName,
        success: true,
        execution_time: executionTime,
        result: result,
        parameters: execParams,
      };
      
      const newHistory = [historyEntry, ...executionHistory.slice(0, 99)];
      setExecutionHistory(newHistory);
      localStorage.setItem('mcp_execution_history', JSON.stringify(newHistory));
      updatePerformanceMetrics(newHistory);
      
      setSuccess(`工具 ${toolName} 执行成功，耗时 ${executionTime}ms`);
      
    } catch (err: any) {
      const historyEntry: ExecutionHistory = {
        id: Date.now().toString(),
        timestamp: new Date(),
        tool_id: toolId,
        tool_name: toolName,
        success: false,
        execution_time: 0,
        result: null,
        error: '工具执行失败，请检查参数或服务状态。',
        errorType: err.code === 'ECONNABORTED' ? 'timeout' : 'network',
        parameters: parameters || toolParameters[toolId],
      };
      
      const newHistory = [historyEntry, ...executionHistory.slice(0, 99)];
      setExecutionHistory(newHistory);
      localStorage.setItem('mcp_execution_history', JSON.stringify(newHistory));
      updatePerformanceMetrics(newHistory);
      
      setError({
        type: err.code === 'ECONNABORTED' ? 'timeout' : 'network',
        message: '工具执行失败，请检查参数或服务状态。',
        timestamp: new Date(),
        retryable: true,
        details: err.response?.data,
      });
    } finally {
      setLoading(false);
    }
  };

  const handleBulkExecute = async () => {
    if (selectedTools.length === 0) return;
    
    setBulkExecuting(true);
    setError(null);
    
    const results = await Promise.allSettled(
      selectedTools.map(toolId => {
        const tool = tools.find(t => t.tool_id === toolId);
        return handleExecuteTool(toolId, tool?.name || toolId);
      })
    );
    
    const failed = results.filter(r => r.status === 'rejected').length;
    if (failed > 0) {
      setError({
        type: 'execution',
        message: `${selectedTools.length} 个工具中有 ${failed} 个执行失败`,
        timestamp: new Date(),
        retryable: false,
      });
    } else {
      setSuccess(`全部 ${selectedTools.length} 个工具均执行成功`);
    }
    
    setSelectedTools([]);
    setBulkExecuting(false);
  };

  // Filtered and sorted tools
  const filteredTools = useMemo(() => {
    let filtered = tools;
    
    if (toolFilters.category) {
      filtered = filtered.filter(t => t.category === toolFilters.category);
    }
    if (toolFilters.source) {
      filtered = filtered.filter(t => t.source === toolFilters.source);
    }
    if (toolFilters.search) {
      const searchLower = toolFilters.search.toLowerCase();
      filtered = filtered.filter(t => 
        t.name.toLowerCase().includes(searchLower) ||
        t.description.toLowerCase().includes(searchLower) ||
        t.tool_id.toLowerCase().includes(searchLower)
      );
    }
    
    // Sort
    filtered.sort((a, b) => {
      if (toolSortBy === 'name') return a.name.localeCompare(b.name);
      if (toolSortBy === 'category') return a.category.localeCompare(b.category);
      return a.source.localeCompare(b.source);
    });
    
    return filtered;
  }, [tools, toolFilters, toolSortBy]);

  // Filtered history
  const filteredHistory = useMemo(() => {
    let filtered = executionHistory;
    
    if (historyFilters.tool) {
      filtered = filtered.filter(h => 
        h.tool_id === historyFilters.tool || h.tool_name.toLowerCase().includes(historyFilters.tool.toLowerCase())
      );
    }
    if (historyFilters.status !== 'all') {
      filtered = filtered.filter(h => 
        historyFilters.status === 'success' ? h.success : !h.success
      );
    }
    if (historyFilters.dateRange !== 'all') {
      const now = new Date();
      let cutoff: Date;
      if (historyFilters.dateRange === 'today') {
        cutoff = new Date(now.setHours(0, 0, 0, 0));
      } else if (historyFilters.dateRange === 'week') {
        cutoff = subDays(now, 7);
      } else {
        cutoff = subDays(now, 30);
      }
      filtered = filtered.filter(h => h.timestamp >= cutoff);
    }
    if (historyFilters.search) {
      const searchLower = historyFilters.search.toLowerCase();
      filtered = filtered.filter(h =>
        h.tool_name.toLowerCase().includes(searchLower) ||
        h.tool_id.toLowerCase().includes(searchLower) ||
        (h.error && h.error.toLowerCase().includes(searchLower))
      );
    }
    
    return filtered;
  }, [executionHistory, historyFilters]);

  // Chart data
  const chartData = useMemo(() => {
    const last30Days = executionHistory
      .filter(h => h.timestamp >= subDays(new Date(), 30))
      .sort((a, b) => a.timestamp.getTime() - b.timestamp.getTime());
    
    // Group by date
    const grouped = last30Days.reduce((acc, entry) => {
      const date = formatDate(entry.timestamp, 'yyyy-MM-dd');
      if (!acc[date]) {
        acc[date] = { date, success: 0, failed: 0, avgTime: 0, count: 0 };
      }
      if (entry.success) {
        acc[date].success++;
      } else {
        acc[date].failed++;
      }
      acc[date].avgTime += entry.execution_time;
      acc[date].count++;
      return acc;
    }, {} as Record<string, { date: string; success: number; failed: number; avgTime: number; count: number }>);
    
    return Object.values(grouped).map(d => ({
      ...d,
      avgTime: d.count > 0 ? Math.round(d.avgTime / d.count) : 0,
    }));
  }, [executionHistory]);

  const toolUsageData = useMemo(() => {
    const usage = executionHistory.reduce((acc, entry) => {
      acc[entry.tool_name] = (acc[entry.tool_name] || 0) + 1;
      return acc;
    }, {} as Record<string, number>);
    
    return Object.entries(usage)
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 10);
  }, [executionHistory]);

  const exportHistory = (format: 'csv' | 'json') => {
    const data = filteredHistory.map(entry => ({
      timestamp: entry.timestamp.toISOString(),
      tool_id: entry.tool_id,
      tool_name: entry.tool_name,
      success: entry.success,
      execution_time: entry.execution_time,
      error: entry.error || '',
    }));
    
    if (format === 'csv') {
      const csv = Papa.unparse(data);
      const blob = new Blob([csv], { type: 'text/csv' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `mcp-execution-history-${formatDate(new Date(), 'yyyy-MM-dd')}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } else {
      const json = JSON.stringify(data, null, 2);
      const blob = new Blob([json], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `mcp-execution-history-${formatDate(new Date(), 'yyyy-MM-dd')}.json`;
      a.click();
      URL.revokeObjectURL(url);
    }
    
    setSuccess(`历史记录已导出为 ${format.toUpperCase()}`);
  };

  const clearHistory = () => {
    if (window.confirm('确定要清空全部执行历史记录吗？')) {
      setExecutionHistory([]);
      localStorage.removeItem('mcp_execution_history');
      updatePerformanceMetrics([]);
      setSuccess('执行历史记录已清空');
    }
  };

  const renderParameterForm = (tool: MCPTool) => {
    if (!tool.parameters || typeof tool.parameters !== 'object') {
      return (
        <Alert severity="info">
          此工具无需参数。
        </Alert>
      );
    }
    
    const schema = tool.parameters;
    const properties = schema.properties || {};
    const required = schema.required || [];
    const currentParams = toolParameters[tool.tool_id] || {};
    const error = parameterErrors[tool.tool_id];
    
    return (
      <Box>
        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}
        {Object.entries(properties).map(([key, prop]: [string, any]) => {
          const isRequired = required.includes(key);
          const value = currentParams[key] ?? (prop.default !== undefined ? prop.default : '');
          
          return (
            <TextField
              key={key}
              fullWidth
              label={key}
              required={isRequired}
              value={value}
              onChange={(e) => {
                let newValue: any = e.target.value;
                if (prop.type === 'number') {
                  newValue = e.target.value === '' ? '' : Number(e.target.value);
                } else if (prop.type === 'boolean') {
                  newValue = e.target.value === 'true';
                } else if (prop.type === 'array') {
                  try {
                    newValue = JSON.parse(e.target.value);
                  } catch {
                    newValue = e.target.value;
                  }
                }
                
                const updated = { ...currentParams, [key]: newValue };
                setToolParameters({ ...toolParameters, [tool.tool_id]: updated });
                
                // Validate
                const validationError = validateParameters(tool, updated);
                if (validationError) {
                  setParameterErrors({ ...parameterErrors, [tool.tool_id]: validationError });
                } else {
                  const newErrors = { ...parameterErrors };
                  delete newErrors[tool.tool_id];
                  setParameterErrors(newErrors);
                }
              }}
              type={prop.type === 'number' ? 'number' : prop.type === 'boolean' ? 'text' : 'text'}
              helperText={prop.description
                ? translateMcpParameterDescription(prop.description, key)
                : (isRequired ? '必填' : '可选')}
              error={!!error && isRequired && !value}
              sx={{ mb: 2 }}
            />
          );
        })}
      </Box>
    );
  };

  const renderToolDetails = (tool: MCPTool) => (
    <Collapse in={showToolDetails === tool.tool_id} timeout="auto" unmountOnExit>
      <Box sx={{ mt: 2, p: 2, bgcolor: 'grey.50', borderRadius: 1 }}>
        <Typography variant="subtitle2" gutterBottom>工具详情：</Typography>
        <Typography variant="body2" sx={{ mb: 1 }}>
          <strong>ID:</strong> {tool.tool_id}
        </Typography>
        <Typography variant="body2" sx={{ mb: 1 }}>
          <strong>来源：</strong> {tool.source}
        </Typography>
        <Typography variant="body2" sx={{ mb: 1 }}>
          <strong>类别：</strong> {translateMcpCategory(tool.category)}
        </Typography>
        <Typography variant="body2" sx={{ mb: 1 }}>
          <strong>能力：</strong> {tool.capabilities?.map(translateMcpCapability).join('、') || '无'}
        </Typography>
        {tool.parameters && (
          <Box sx={{ mb: 2 }}>
            <Typography variant="body2" sx={{ mb: 1 }}>
              <strong>参数：</strong>
            </Typography>
            <Paper sx={{ p: 1, bgcolor: 'white', maxHeight: 200, overflow: 'auto' }}>
              <JsonView
                value={tool.parameters}
                collapsed={1}
              />
            </Paper>
          </Box>
        )}
        {tool.metadata && (
          <Box>
            <Typography variant="body2" sx={{ mb: 1 }}>
              <strong>元数据：</strong>
            </Typography>
            <Paper sx={{ p: 1, bgcolor: 'white', maxHeight: 200, overflow: 'auto' }}>
              <JsonView
                value={tool.metadata}
                collapsed={1}
              />
            </Paper>
          </Box>
        )}
      </Box>
    </Collapse>
  );

  const getStatusLabel = (status: unknown) => {
    const normalizedStatus = String(status);
    const labels: Record<string, string> = {
      operational: '运行正常',
      connected: '已连接',
      disconnected: '未连接',
      checking: '检查中',
      running: '运行中',
      stopped: '已停止',
      success: '成功',
      failed: '失败',
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

  const getErrorTypeLabel = (type: ErrorDetails['type']) => {
    const labels: Record<ErrorDetails['type'], string> = {
      network: '网络错误',
      validation: '验证错误',
      execution: '执行错误',
      timeout: '超时错误',
    };
    return labels[type];
  };

  return (
    <Box sx={{ p: 2, bgcolor: 'background.default', minHeight: '100vh' }}>
      {/* Header with connection status and controls */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Typography variant="h5" gutterBottom>
          增强型 MCP 测试仪表板
        </Typography>
        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
          {/* Connection Status */}
          <Tooltip title={getStatusLabel(connectionStatus)}>
            <Chip
              icon={connectionStatus === 'connected' ? <WifiIcon /> : <WifiOffIcon />}
              label={getStatusLabel(connectionStatus)}
              color={connectionStatus === 'connected' ? 'success' : 'error'}
              size="small"
            />
          </Tooltip>
          
          {/* Auto-refresh toggle */}
          <FormControlLabel
            control={
              <Switch
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
                size="small"
              />
            }
            label="自动刷新"
          />
        </Box>
      </Box>

      {/* Stale data indicator */}
      {dataStale && (
        <Alert 
          severity="warning" 
          sx={{ mb: 2 }}
          action={
            <Button color="inherit" size="small" onClick={() => loadMcpData()}>
              立即刷新
            </Button>
          }
        >
          数据可能已过期。上次更新时间：{formatDate(lastUpdateTime, 'HH:mm:ss')}
        </Alert>
      )}

      {/* Enhanced Error Display */}
      {error && (
        <Alert 
          severity="error" 
          sx={{ mb: 2 }}
          onClose={() => setError(null)}
          action={
            error.retryable && (
              <Button color="inherit" size="small" onClick={handleRetry} startIcon={<RetryIcon />}>
                重试
              </Button>
            )
          }
        >
          <Typography variant="body2" fontWeight="bold">
            {getErrorTypeLabel(error.type)}：{error.message}
          </Typography>
          <Collapse in={true}>
            <Box sx={{ mt: 1 }}>
              <Typography variant="caption">
                时间戳：{formatDate(error.timestamp, 'yyyy-MM-dd HH:mm:ss')}
              </Typography>
              {error.details && (
                <Box sx={{ mt: 1 }}>
                  <Typography variant="caption" fontWeight="bold">详情：</Typography>
                  <Paper sx={{ p: 1, mt: 0.5, bgcolor: 'rgba(0,0,0,0.05)', maxHeight: 200, overflow: 'auto' }}>
                    <JsonView
                      value={error.details}
                      collapsed={2}
                    />
                  </Paper>
                </Box>
              )}
            </Box>
          </Collapse>
        </Alert>
      )}

      {success && (
        <Alert severity="success" sx={{ mb: 2 }} onClose={() => setSuccess(null)}>
          {success}
        </Alert>
      )}

      {/* Performance Metrics */}
      <Grid container spacing={2} sx={{ mb: 3 }}>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                <PlayIcon color="primary" sx={{ mr: 1 }} />
                <Box>
                  <Typography variant="h6">{performanceMetrics.totalExecutions}</Typography>
                  <Typography variant="body2" color="text.secondary">执行总数</Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                <CheckCircleIcon color="success" sx={{ mr: 1 }} />
                <Box>
                  <Typography variant="h6">{performanceMetrics.successRate.toFixed(1)}%</Typography>
                  <Typography variant="body2" color="text.secondary">成功率</Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                <SpeedIcon color="info" sx={{ mr: 1 }} />
                <Box>
                  <Typography variant="h6">{performanceMetrics.averageExecutionTime.toFixed(0)}ms</Typography>
                  <Typography variant="body2" color="text.secondary">平均执行时间</Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                <AssessmentIcon color="warning" sx={{ mr: 1 }} />
                <Box>
                  <Typography variant="h6">{mcpStatus?.tool_discovery.discovered_tools || 0}</Typography>
                  <Typography variant="body2" color="text.secondary">可用工具</Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 2 }}>
        <Tabs value={tabValue} onChange={(e, newValue) => setTabValue(newValue)}>
          <Tab label="状态与发现" />
          <Tab label="工具搜索" />
          <Tab label="工作流测试" />
          <Tab label="执行历史" />
          <Tab label="分析" />
        </Tabs>
      </Box>

      {/* Status & Discovery Tab */}
      <TabPanel value={tabValue} index={0}>
        <Grid container spacing={2}>
          {agentsStatus && (
            <Grid item xs={12}>
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    智能体状态
                  </Typography>
                  <Grid container spacing={2}>
                    {Object.entries(agentsStatus.agents || {}).map(([agentName, agentInfo]: [string, any]) => (
                      <Grid item xs={12} sm={6} md={4} key={agentName}>
                        <Paper sx={{ p: 2, bgcolor: agentInfo.status === 'operational' ? 'success.light' : 'error.light' }}>
                          <Typography variant="subtitle1" fontWeight="bold" sx={{ textTransform: 'capitalize' }}>
                            {translateMcpCategory(agentName)}
                          </Typography>
                          <Chip 
                            label={getStatusLabel(agentInfo.status)} 
                            color={agentInfo.status === 'operational' ? 'success' : 'error'}
                            size="small"
                            sx={{ mt: 1, mb: 1 }}
                          />
                          <Typography variant="body2">
                            MCP 已启用：{agentInfo.mcp_enabled ? '是' : '否'}
                          </Typography>
                          <Typography variant="body2">
                            可用工具：{agentInfo.tool_count || 0}
                          </Typography>
                          {agentInfo.note && (
                            <Typography variant="caption" color="text.secondary">
                              {translateMcpAgentNote(agentInfo.note)}
                            </Typography>
                          )}
                        </Paper>
                      </Grid>
                    ))}
                  </Grid>
                </CardContent>
              </Card>
            </Grid>
          )}

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
                  <Skeleton variant="rectangular" height={200} />
                )}
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} md={6}>
            <Card>
              <CardContent>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                  <Typography variant="h6">
                    已发现工具（{filteredTools.length}）
                  </Typography>
                  <Box sx={{ display: 'flex', gap: 1 }}>
                    <IconButton size="small" onClick={() => setShowFilters(!showFilters)}>
                      <FilterIcon />
                    </IconButton>
                    <FormControl size="small" sx={{ minWidth: 120 }}>
                      <InputLabel>排序方式</InputLabel>
                      <Select
                        value={toolSortBy}
                        label="排序方式"
                        onChange={(e) => setToolSortBy(e.target.value as any)}
                      >
                        <MenuItem value="name">名称</MenuItem>
                        <MenuItem value="category">类别</MenuItem>
                        <MenuItem value="source">来源</MenuItem>
                      </Select>
                    </FormControl>
                  </Box>
                </Box>

                {/* Filters */}
                <Collapse in={showFilters}>
                  <Box sx={{ mb: 2, p: 2, bgcolor: 'grey.50', borderRadius: 1 }}>
                    <Grid container spacing={2}>
                      <Grid item xs={12} md={4}>
                        <FormControl fullWidth size="small">
                          <InputLabel>类别</InputLabel>
                          <Select
                            value={toolFilters.category}
                            label="类别"
                            onChange={(e) => setToolFilters({ ...toolFilters, category: e.target.value })}
                          >
                            <MenuItem value="">全部</MenuItem>
                            {Array.from(new Set(tools.map(t => t.category))).map(cat => (
                              <MenuItem key={cat} value={cat}>{translateMcpCategory(cat)}</MenuItem>
                            ))}
                          </Select>
                        </FormControl>
                      </Grid>
                      <Grid item xs={12} md={4}>
                        <FormControl fullWidth size="small">
                          <InputLabel>来源</InputLabel>
                          <Select
                            value={toolFilters.source}
                            label="来源"
                            onChange={(e) => setToolFilters({ ...toolFilters, source: e.target.value })}
                          >
                            <MenuItem value="">全部</MenuItem>
                            {Array.from(new Set(tools.map(t => t.source))).map(src => (
                              <MenuItem key={src} value={src}>{src}</MenuItem>
                            ))}
                          </Select>
                        </FormControl>
                      </Grid>
                      <Grid item xs={12} md={4}>
                        <TextField
                          fullWidth
                          size="small"
                          label="搜索"
                          value={toolFilters.search}
                          onChange={(e) => setToolFilters({ ...toolFilters, search: e.target.value })}
                        />
                      </Grid>
                    </Grid>
                    <Button
                      size="small"
                      startIcon={<ClearIcon />}
                      onClick={() => setToolFilters({ category: '', source: '', search: '' })}
                      sx={{ mt: 1 }}
                    >
                      清除筛选条件
                    </Button>
                  </Box>
                </Collapse>

                {/* Bulk selection */}
                {selectedTools.length > 0 && (
                  <Alert severity="info" sx={{ mb: 2 }}>
                    已选择 {selectedTools.length} 个工具
                    <Button size="small" onClick={handleBulkExecute} disabled={bulkExecuting} sx={{ ml: 2 }}>
                      执行所选工具
                    </Button>
                    <Button size="small" onClick={() => setSelectedTools([])} sx={{ ml: 1 }}>
                      清除选择
                    </Button>
                  </Alert>
                )}
                
                {filteredTools.length > 0 ? (
                  <List dense>
                    {filteredTools.map((tool) => (
                      <React.Fragment key={tool.tool_id}>
                        <ListItem>
                          <Checkbox
                            checked={selectedTools.includes(tool.tool_id)}
                            onChange={(e) => {
                              if (e.target.checked) {
                                setSelectedTools([...selectedTools, tool.tool_id]);
                              } else {
                                setSelectedTools(selectedTools.filter(id => id !== tool.tool_id));
                              }
                            }}
                            sx={{ mr: 1 }}
                          />
                          <ListItemText
                            primary={tool.name}
                            secondaryTypographyProps={{ component: 'div' }}
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
                            <Tooltip title="查看详情">
                              <IconButton
                                edge="end"
                                onClick={() => setShowToolDetails(
                                  showToolDetails === tool.tool_id ? null : tool.tool_id
                                )}
                              >
                                <VisibilityIcon />
                              </IconButton>
                            </Tooltip>
                            <Tooltip title="执行工具">
                              <IconButton
                                edge="end"
                                onClick={() => {
                                  if (tool.parameters && Object.keys(tool.parameters).length > 0) {
                                    setSelectedToolForExecution(tool);
                                    setShowParameterDialog(true);
                                  } else {
                                    handleExecuteTool(tool.tool_id, tool.name);
                                  }
                                }}
                                disabled={loading}
                                sx={{ ml: 1 }}
                              >
                                <PlayIcon />
                              </IconButton>
                            </Tooltip>
                          </ListItemSecondaryAction>
                        </ListItem>
                        {renderToolDetails(tool)}
                      </React.Fragment>
                    ))}
                  </List>
                ) : (
                  <Typography variant="body2" color="text.secondary">
                    {tools.length === 0 ? '尚未发现工具，请尝试刷新发现结果。' : '没有工具符合当前筛选条件。'}
                  </Typography>
                )}
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </TabPanel>

      {/* Tool Search Tab */}
      <TabPanel value={tabValue} index={1}>
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              工具搜索
            </Typography>
            
            <Box sx={{ display: 'flex', gap: 1, mb: 2 }}>
              <TextField
                fullWidth
                label="搜索工具..."
                placeholder="按 Ctrl/Cmd + K 聚焦搜索框"
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
                          onClick={() => handleExecuteTool(tool.tool_id, tool.name)}
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
      </TabPanel>

      {/* Workflow Testing Tab */}
      <TabPanel value={tabValue} index={2}>
        <Grid container spacing={2}>
          <Grid item xs={12} md={8}>
            <Card>
              <CardContent>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                  <Typography variant="h6">
                    MCP 工作流测试
                  </Typography>
                  <Box sx={{ display: 'flex', gap: 1 }}>
                    <Button
                      size="small"
                      startIcon={<SaveIcon />}
                      onClick={() => setShowScenarioDialog(true)}
                    >
                      保存场景
                    </Button>
                    <Button
                      size="small"
                      startIcon={<UploadIcon />}
                      onClick={() => {
                        const input = document.createElement('input');
                        input.type = 'file';
                        input.accept = '.json';
                        input.onchange = (e: any) => {
                          const file = e.target.files[0];
                          const reader = new FileReader();
                          reader.onload = (event) => {
                            try {
                              const scenario = JSON.parse(event.target?.result as string);
                              loadTestScenario(scenario);
                            } catch (err) {
                              setError({
                                type: 'validation',
                                message: '场景文件无效',
                                timestamp: new Date(),
                                retryable: false,
                              });
                            }
                          };
                          reader.readAsText(file);
                        };
                        input.click();
                      }}
                    >
                      加载场景
                    </Button>
                  </Box>
                </Box>
                
                <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                  使用示例消息测试完整的 MCP 工作流（按 Ctrl/Cmd + Enter 执行）：
                </Typography>
                
                {/* Test Scenarios */}
                {testScenarios.length > 0 && (
                  <Box sx={{ mb: 2 }}>
                    <Typography variant="subtitle2" gutterBottom>已保存场景：</Typography>
                    <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                      {testScenarios.slice(0, 5).map((scenario) => (
                        <Chip
                          key={scenario.id}
                          label={scenario.name}
                          onClick={() => loadTestScenario(scenario)}
                          onDelete={() => {
                            const updated = testScenarios.filter(s => s.id !== scenario.id);
                            setTestScenarios(updated);
                            localStorage.setItem('mcp_test_scenarios', JSON.stringify(updated));
                          }}
                          sx={{ mb: 1 }}
                        />
                      ))}
                    </Box>
                  </Box>
                )}
                
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
                  <Button
                    variant="outlined"
                    size="small"
                    onClick={() => setTestMessage('为 SKU-12345 生成需求预测。')}
                  >
                    需求预测
                  </Button>
                  <Button
                    variant="outlined"
                    size="small"
                    onClick={() => setTestMessage('显示补货建议。')}
                  >
                    补货建议
                  </Button>
                  <Button
                    variant="outlined"
                    size="small"
                    onClick={() => setTestMessage('上传并处理一份文档。')}
                  >
                    文档处理
                  </Button>
                </Box>
                
                <Box sx={{ display: 'flex', gap: 1, mb: 2 }}>
                  <TextField
                    fullWidth
                    label="测试消息..."
                    value={testMessage}
                    onChange={(e) => setTestMessage(e.target.value)}
                    placeholder="例如：显示叉车 FL-001 的状态"
                    multiline
                    rows={3}
                  />
                  <Button
                    variant="contained"
                    startIcon={loading ? <CircularProgress size={16} /> : <PlayIcon />}
                    onClick={handleTestWorkflow}
                    disabled={loading || !testMessage.trim()}
                    sx={{ alignSelf: 'flex-start' }}
                  >
                    {loading ? '正在测试...' : '测试工作流'}
                  </Button>
                </Box>
                
                {testResult && (
                  <Paper sx={{ p: 2, bgcolor: 'grey.50' }}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                      <Typography variant="subtitle2">
                        工作流测试结果：
                      </Typography>
                      <CopyToClipboard text={JSON.stringify(testResult, null, 2)}>
                        <IconButton size="small">
                          <CopyIcon />
                        </IconButton>
                      </CopyToClipboard>
                    </Box>
                    <Box sx={{ maxHeight: 400, overflow: 'auto' }}>
                      <JsonView
                        value={testResult}
                        collapsed={2}
                      />
                    </Box>
                  </Paper>
                )}
              </CardContent>
            </Card>
          </Grid>
          
          <Grid item xs={12} md={4}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  测试场景
                </Typography>
                {testScenarios.length > 0 ? (
                  <List dense>
                    {testScenarios.map((scenario) => (
                      <ListItem key={scenario.id}>
                        <ListItemText
                          primary={scenario.name}
                          secondary={scenario.description || scenario.message.substring(0, 50) + '...'}
                        />
                        <ListItemSecondaryAction>
                          <IconButton size="small" onClick={() => loadTestScenario(scenario)}>
                            <PlayIcon />
                          </IconButton>
                          <IconButton size="small" onClick={() => shareScenario(scenario)}>
                            <CopyIcon />
                          </IconButton>
                        </ListItemSecondaryAction>
                      </ListItem>
                    ))}
                  </List>
                ) : (
                  <Typography variant="body2" color="text.secondary">
                    暂无已保存场景。保存一条测试消息即可创建场景。
                  </Typography>
                )}
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </TabPanel>

      {/* Execution History Tab */}
      <TabPanel value={tabValue} index={3}>
        <Card>
          <CardContent>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
              <Typography variant="h6">
                执行历史
              </Typography>
              <Box sx={{ display: 'flex', gap: 1 }}>
                {selectedHistoryEntries.length > 0 && (
                  <>
                    <Button
                      size="small"
                      startIcon={<CompareIcon />}
                      onClick={() => setShowComparisonDialog(true)}
                      disabled={selectedHistoryEntries.length < 2}
                    >
                      比较（{selectedHistoryEntries.length}）
                    </Button>
                  </>
                )}
                <Button
                  size="small"
                  startIcon={<DownloadIcon />}
                  onClick={() => exportHistory('json')}
                  disabled={filteredHistory.length === 0}
                >
                  导出 JSON
                </Button>
                <Button
                  size="small"
                  startIcon={<DownloadIcon />}
                  onClick={() => exportHistory('csv')}
                  disabled={filteredHistory.length === 0}
                >
                  导出 CSV
                </Button>
                <Button
                  size="small"
                  startIcon={<DeleteIcon />}
                  onClick={clearHistory}
                  disabled={executionHistory.length === 0}
                  color="error"
                >
                  清空
                </Button>
              </Box>
            </Box>

            {/* History Filters */}
            <Box sx={{ mb: 2, p: 2, bgcolor: 'grey.50', borderRadius: 1 }}>
              <Grid container spacing={2}>
                <Grid item xs={12} md={3}>
                  <TextField
                    fullWidth
                    size="small"
                    label="搜索"
                    value={historyFilters.search}
                    onChange={(e) => setHistoryFilters({ ...historyFilters, search: e.target.value })}
                  />
                </Grid>
                <Grid item xs={12} md={3}>
                  <FormControl fullWidth size="small">
                    <InputLabel>工具</InputLabel>
                    <Select
                      value={historyFilters.tool}
                      label="工具"
                      onChange={(e) => setHistoryFilters({ ...historyFilters, tool: e.target.value })}
                    >
                      <MenuItem value="">全部</MenuItem>
                      {Array.from(new Set(executionHistory.map(h => h.tool_name))).map(tool => (
                        <MenuItem key={tool} value={tool}>{tool}</MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Grid>
                <Grid item xs={12} md={3}>
                  <FormControl fullWidth size="small">
                    <InputLabel>状态</InputLabel>
                    <Select
                      value={historyFilters.status}
                      label="状态"
                      onChange={(e) => setHistoryFilters({ ...historyFilters, status: e.target.value as any })}
                    >
                      <MenuItem value="all">全部</MenuItem>
                      <MenuItem value="success">成功</MenuItem>
                      <MenuItem value="failed">失败</MenuItem>
                    </Select>
                  </FormControl>
                </Grid>
                <Grid item xs={12} md={3}>
                  <FormControl fullWidth size="small">
                    <InputLabel>日期范围</InputLabel>
                    <Select
                      value={historyFilters.dateRange}
                      label="日期范围"
                      onChange={(e) => setHistoryFilters({ ...historyFilters, dateRange: e.target.value as any })}
                    >
                      <MenuItem value="all">全部</MenuItem>
                      <MenuItem value="today">今天</MenuItem>
                      <MenuItem value="week">最近一周</MenuItem>
                      <MenuItem value="month">最近一个月</MenuItem>
                    </Select>
                  </FormControl>
                </Grid>
              </Grid>
            </Box>
            
            {filteredHistory.length > 0 ? (
              <TableContainer>
                <Table>
                  <TableHead>
                    <TableRow>
                      <TableCell padding="checkbox">
                        <Checkbox
                          indeterminate={selectedHistoryEntries.length > 0 && selectedHistoryEntries.length < filteredHistory.length}
                          checked={filteredHistory.length > 0 && selectedHistoryEntries.length === filteredHistory.length}
                          onChange={(e) => {
                            if (e.target.checked) {
                              setSelectedHistoryEntries(filteredHistory.map(h => h.id));
                            } else {
                              setSelectedHistoryEntries([]);
                            }
                          }}
                        />
                      </TableCell>
                      <TableCell>时间戳</TableCell>
                      <TableCell>工具</TableCell>
                      <TableCell>状态</TableCell>
                      <TableCell>执行时间</TableCell>
                      <TableCell>操作</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {filteredHistory.map((entry) => (
                      <TableRow key={entry.id}>
                        <TableCell padding="checkbox">
                          <Checkbox
                            checked={selectedHistoryEntries.includes(entry.id)}
                            onChange={(e) => {
                              if (e.target.checked) {
                                setSelectedHistoryEntries([...selectedHistoryEntries, entry.id]);
                              } else {
                                setSelectedHistoryEntries(selectedHistoryEntries.filter(id => id !== entry.id));
                              }
                            }}
                          />
                        </TableCell>
                        <TableCell>
                          {formatDate(entry.timestamp, 'yyyy-MM-dd HH:mm:ss')}
                        </TableCell>
                        <TableCell>
                          <Typography variant="body2" fontWeight="medium">
                            {entry.tool_name}
                          </Typography>
                          <Typography variant="caption" color="text.secondary">
                            {entry.tool_id}
                          </Typography>
                        </TableCell>
                        <TableCell>
                          <Chip
                            icon={entry.success ? <CheckCircleIcon /> : <ErrorIcon />}
                            label={entry.success ? '成功' : '失败'}
                            color={entry.success ? 'success' : 'error'}
                            size="small"
                          />
                        </TableCell>
                        <TableCell>
                          {entry.execution_time}ms
                        </TableCell>
                        <TableCell>
                          <Tooltip title="查看详情">
                            <IconButton 
                              size="small"
                              onClick={() => setSelectedHistoryEntry(entry)}
                            >
                              <InfoIcon />
                            </IconButton>
                          </Tooltip>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            ) : (
              <Typography variant="body2" color="text.secondary">
                {executionHistory.length === 0 
                  ? '暂无执行历史。执行一些工具后即可查看记录。'
                  : '没有历史记录符合当前筛选条件。'}
              </Typography>
            )}
          </CardContent>
        </Card>
      </TabPanel>

      {/* Analytics Tab */}
      <TabPanel value={tabValue} index={4}>
        <Grid container spacing={2}>
          <Grid item xs={12}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  执行时间趋势
                </Typography>
                {chartData.length > 0 ? (
                  <ResponsiveContainer width="100%" height={300}>
                    <LineChart data={chartData}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="date" />
                      <YAxis />
                      <RechartsTooltip />
                      <Legend />
                      <Line type="monotone" dataKey="avgTime" stroke="#8884d8" name="平均执行时间（ms）" />
                    </LineChart>
                  </ResponsiveContainer>
                ) : (
                  <Typography variant="body2" color="text.secondary">
                    最近 30 天暂无数据
                  </Typography>
                )}
              </CardContent>
            </Card>
          </Grid>
          
          <Grid item xs={12} md={6}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  成功率趋势
                </Typography>
                {chartData.length > 0 ? (
                  <ResponsiveContainer width="100%" height={300}>
                    <LineChart data={chartData}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="date" />
                      <YAxis />
                      <RechartsTooltip />
                      <Legend />
                      <Line type="monotone" dataKey="success" stroke="#82ca9d" name="成功" />
                      <Line type="monotone" dataKey="failed" stroke="#ff7300" name="失败" />
                    </LineChart>
                  </ResponsiveContainer>
                ) : (
                  <Typography variant="body2" color="text.secondary">
                    暂无数据
                  </Typography>
                )}
              </CardContent>
            </Card>
          </Grid>
          
          <Grid item xs={12} md={6}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  工具使用分布
                </Typography>
                {toolUsageData.length > 0 ? (
                  <ResponsiveContainer width="100%" height={300}>
                    <BarChart data={toolUsageData}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="name" angle={-45} textAnchor="end" height={100} />
                      <YAxis />
                      <RechartsTooltip />
                      <Bar dataKey="count" fill="#8884d8" name="使用次数" />
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <Typography variant="body2" color="text.secondary">
                    暂无工具使用数据
                  </Typography>
                )}
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </TabPanel>

      {/* Parameter Input Dialog */}
      <Dialog
        open={showParameterDialog}
        onClose={() => setShowParameterDialog(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>
          执行工具：{selectedToolForExecution?.name}
        </DialogTitle>
        <DialogContent>
          {selectedToolForExecution && (
            <>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                {translateMcpDescription(
                  selectedToolForExecution.description,
                  selectedToolForExecution.name,
                )}
              </Typography>
              {renderParameterForm(selectedToolForExecution)}
            </>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowParameterDialog(false)}>取消</Button>
          <Button
            variant="contained"
            onClick={() => {
              if (selectedToolForExecution) {
                handleExecuteTool(
                  selectedToolForExecution.tool_id,
                  selectedToolForExecution.name,
                  toolParameters[selectedToolForExecution.tool_id]
                );
                setShowParameterDialog(false);
              }
            }}
            disabled={!!parameterErrors[selectedToolForExecution?.tool_id || '']}
          >
            执行
          </Button>
        </DialogActions>
      </Dialog>

      {/* Execution History Details Dialog */}
      <Dialog
        open={!!selectedHistoryEntry}
        onClose={() => setSelectedHistoryEntry(null)}
        maxWidth="md"
        fullWidth
      >
        {selectedHistoryEntry && (
          <>
            <DialogTitle>
              执行详情：{selectedHistoryEntry.tool_name}
            </DialogTitle>
            <DialogContent>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                {formatDate(selectedHistoryEntry.timestamp, 'yyyy-MM-dd HH:mm:ss')}
              </Typography>
              <Divider sx={{ my: 2 }} />
              <Typography variant="subtitle2" gutterBottom>
                状态：{selectedHistoryEntry.success ? '成功' : '失败'}
              </Typography>
              <Typography variant="body2" sx={{ mb: 2 }}>
                执行时间：{selectedHistoryEntry.execution_time}ms
              </Typography>
              {selectedHistoryEntry.error && (
                <Alert severity="error" sx={{ mb: 2 }}>
                  工具执行失败，请检查参数或服务状态。
                </Alert>
              )}
              {selectedHistoryEntry.parameters && (
                <Box sx={{ mb: 2 }}>
                  <Typography variant="subtitle2" gutterBottom>参数：</Typography>
                  <Paper sx={{ p: 1, bgcolor: 'grey.50', maxHeight: 200, overflow: 'auto' }}>
                    <JsonView
                      value={selectedHistoryEntry.parameters}
                      collapsed={1}
                    />
                  </Paper>
                </Box>
              )}
              {selectedHistoryEntry.result && (
                <Box>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                    <Typography variant="subtitle2">结果：</Typography>
                    <CopyToClipboard text={JSON.stringify(selectedHistoryEntry.result, null, 2)}>
                      <IconButton size="small">
                        <CopyIcon />
                      </IconButton>
                    </CopyToClipboard>
                  </Box>
                  <Paper sx={{ p: 1, bgcolor: 'grey.50', maxHeight: 400, overflow: 'auto' }}>
                    <JsonView
                      value={selectedHistoryEntry.result}
                      collapsed={2}
                    />
                  </Paper>
                </Box>
              )}
            </DialogContent>
            <DialogActions>
              <Button onClick={() => setSelectedHistoryEntry(null)}>关闭</Button>
            </DialogActions>
          </>
        )}
      </Dialog>

      {/* Comparison Dialog */}
      <Dialog
        open={showComparisonDialog}
        onClose={() => setShowComparisonDialog(false)}
        maxWidth="lg"
        fullWidth
      >
        <DialogTitle>比较执行结果</DialogTitle>
        <DialogContent>
          <Grid container spacing={2}>
            {selectedHistoryEntries.slice(0, 2).map((id) => {
              const entry = executionHistory.find(e => e.id === id);
              if (!entry) return null;
              return (
                <Grid item xs={12} md={6} key={id}>
                  <Card>
                    <CardContent>
                      <Typography variant="h6">{entry.tool_name}</Typography>
                      <Typography variant="caption" color="text.secondary">
                        {formatDate(entry.timestamp, 'yyyy-MM-dd HH:mm:ss')}
                      </Typography>
                      <Chip
                        label={entry.success ? '成功' : '失败'}
                        color={entry.success ? 'success' : 'error'}
                        size="small"
                        sx={{ ml: 1 }}
                      />
                      <Typography variant="body2" sx={{ mt: 1 }}>
                        执行时间：{entry.execution_time}ms
                      </Typography>
                      {entry.result && (
                        <Box sx={{ mt: 2, maxHeight: 300, overflow: 'auto' }}>
                          <JsonView
                            value={entry.result}
                            collapsed={2}
                          />
                        </Box>
                      )}
                    </CardContent>
                  </Card>
                </Grid>
              );
            })}
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowComparisonDialog(false)}>关闭</Button>
        </DialogActions>
      </Dialog>

      {/* Save Scenario Dialog */}
      <Dialog
        open={showScenarioDialog}
        onClose={() => {
          setShowScenarioDialog(false);
          setSelectedScenario({ name: '', description: '', message: testMessage });
        }}
      >
        <DialogTitle>保存测试场景</DialogTitle>
        <DialogContent>
          <TextField
            fullWidth
            label="场景名称"
            value={selectedScenario.name || ''}
            onChange={(e) => setSelectedScenario({ ...selectedScenario, name: e.target.value })}
            sx={{ mb: 2, mt: 1 }}
          />
          <TextField
            fullWidth
            label="说明（可选）"
            value={selectedScenario.description || ''}
            onChange={(e) => setSelectedScenario({ ...selectedScenario, description: e.target.value })}
            sx={{ mb: 2 }}
          />
          <TextField
            fullWidth
            label="测试消息"
            value={testMessage}
            onChange={(e) => setTestMessage(e.target.value)}
            multiline
            rows={3}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowScenarioDialog(false)}>取消</Button>
          <Button
            variant="contained"
            onClick={() => {
              if (testMessage && selectedScenario.name) {
                saveTestScenario({
                  name: selectedScenario.name,
                  message: testMessage,
                  description: selectedScenario.description,
                });
                setSelectedScenario({ name: '', description: '', message: testMessage });
                setShowScenarioDialog(false);
              }
            }}
            disabled={!testMessage || !selectedScenario.name}
          >
            保存
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default EnhancedMCPTestingPanel;

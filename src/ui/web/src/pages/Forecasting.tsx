import React, { useState } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Grid,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
  Alert,
  CircularProgress,
  IconButton,
  Button,
  Tabs,
  Tab,
  LinearProgress,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  TextField,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Stepper,
  Step,
  StepLabel,
  StepContent,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  Divider,
} from '@mui/material';
import {
  TrendingUp as TrendingUpIcon,
  TrendingDown as TrendingDownIcon,
  TrendingFlat as TrendingFlatIcon,
  Refresh as RefreshIcon,
  Warning as WarningIcon,
  CheckCircle as CheckCircleIcon,
  Analytics as AnalyticsIcon,
  Inventory as InventoryIcon,
  Speed as SpeedIcon,
  PlayArrow as PlayIcon,
  Stop as StopIcon,
  Schedule as ScheduleIcon,
  History as HistoryIcon,
  Build as BuildIcon,
  Error as ErrorIcon,
  Info as InfoIcon,
  Assessment as AssessmentIcon,
  Memory as MemoryIcon,
  Storage as StorageIcon,
  Timeline as TimelineIcon,
  BarChart as BarChartIcon,
  PieChart as PieChartIcon,
  ShowChart as ShowChartIcon,
  Star as StarIcon,
  StarBorder as StarBorderIcon,
  ArrowUpward as ArrowUpwardIcon,
  ArrowDownward as ArrowDownwardIcon,
  Remove as RemoveIcon,
} from '@mui/icons-material';
import { useQuery } from '@tanstack/react-query';
import { forecastingAPI } from '../services/forecastingAPI';
import { trainingAPI, TrainingRequest, TrainingStatus } from '../services/trainingAPI';
import { TabPanel } from '../components/common';
import {
  formatZhDate,
  formatZhDateTime,
  translatePriority,
  translateStatus,
  translateTrainingMessage,
} from '../localization/zhCN';

const trendLabels: Readonly<Record<string, string>> = {
  increasing: '上升',
  decreasing: '下降',
  stable: '稳定',
};

const translateTrend = (trend: string) => trendLabels[trend.toLowerCase()] || trend;

const translateTrainingType = (type: string) => {
  const normalized = type.toLowerCase();
  return normalized === 'advanced' ? '高级' : normalized === 'basic' ? '基础' : type;
};

const translateModelStatus = (status: string) =>
  status.toUpperCase() === 'WARNING' ? '警告' : translateStatus(status);

const ForecastingPage: React.FC = () => {
  const [selectedTab, setSelectedTab] = useState(0);
  
  // Training state
  const [trainingType, setTrainingType] = useState<'basic' | 'advanced'>('advanced');
  const [scheduleDialogOpen, setScheduleDialogOpen] = useState(false);
  const [scheduleTime, setScheduleTime] = useState('');
  const [trainingDialogOpen, setTrainingDialogOpen] = useState(false);

  // Fetch forecasting data - use dashboard endpoint only for faster loading
  const { data: dashboardData, isLoading: dashboardLoading, refetch: refetchDashboard, error: dashboardError } = useQuery({
    queryKey: ['forecasting-dashboard'],
    queryFn: forecastingAPI.getDashboardSummary,
    refetchInterval: 300000, // Refetch every 5 minutes
    retry: 1,
    retryDelay: 200,
    staleTime: 30000, // Consider data fresh for 30 seconds
    gcTime: 300000, // Keep in cache for 5 minutes (renamed from cacheTime in v5)
    refetchOnWindowFocus: false // Don't refetch when window gains focus
  });

  // Fetch training status with polling when training is running
  const { data: trainingStatus, refetch: refetchTrainingStatus } = useQuery({
    queryKey: ['training-status'],
    queryFn: trainingAPI.getTrainingStatus,
    refetchInterval: 2000, // Poll every 2 seconds
    retry: 1,
    retryDelay: 200,
  });

  // Fetch training history
  const { data: trainingHistory } = useQuery({
    queryKey: ['training-history'],
    queryFn: trainingAPI.getTrainingHistory,
    refetchInterval: 60000, // Refetch every minute
    retry: 1,
  });

  const getTrendIcon = (trend: string) => {
    switch (trend) {
      case 'increasing':
        return <TrendingUpIcon color="success" />;
      case 'decreasing':
        return <TrendingDownIcon color="error" />;
      default:
        return <TrendingFlatIcon color="info" />;
    }
  };

  const getUrgencyColor = (urgency: string) => {
    switch (urgency) {
      case 'critical':
        return 'error';
      case 'high':
        return 'warning';
      case 'medium':
        return 'info';
      default:
        return 'success';
    }
  };

  const getAccuracyColor = (accuracy: number) => {
    if (accuracy >= 0.9) return 'success';
    if (accuracy >= 0.8) return 'info';
    if (accuracy >= 0.7) return 'warning';
    return 'error';
  };

  // Training functions
  const handleStartTraining = async () => {
    try {
      const request: TrainingRequest = {
        training_type: trainingType,
        force_retrain: true
      };
      await trainingAPI.startTraining(request);
      setTrainingDialogOpen(true);
      refetchTrainingStatus();
    } catch (error) {
      console.error('Failed to start training:', error);
    }
  };

  const handleStopTraining = async () => {
    try {
      await trainingAPI.stopTraining();
      refetchTrainingStatus();
    } catch (error) {
      console.error('Failed to stop training:', error);
    }
  };

  const handleScheduleTraining = async () => {
    try {
      const request: TrainingRequest = {
        training_type: trainingType,
        force_retrain: true,
        schedule_time: scheduleTime
      };
      await trainingAPI.scheduleTraining(request);
      setScheduleDialogOpen(false);
      setScheduleTime('');
    } catch (error) {
      console.error('Failed to schedule training:', error);
    }
  };

  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setSelectedTab(newValue);
  };

  // Show error if there are issues
  if (dashboardError) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="error" sx={{ mb: 2 }}>
          预测数据加载失败，请检查服务连接后重试。
        </Alert>
        <Button onClick={() => {
          refetchDashboard();
        }} variant="contained">
          重试
        </Button>
      </Box>
    );
  }

  if (dashboardLoading) {
    return (
      <Box sx={{ p: 3 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
          <Typography variant="h4" component="h1" gutterBottom>
            需求预测仪表板
          </Typography>
          <CircularProgress size={24} />
        </Box>
        
        {/* Show skeleton loading for cards */}
        <Grid container spacing={3} sx={{ mb: 3 }}>
          {[1, 2, 3, 4].map((i) => (
            <Grid item xs={12} sm={6} md={3} key={i}>
              <Card>
                <CardContent>
                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                    <CircularProgress size={20} sx={{ mr: 1 }} />
                    <Typography variant="h6">正在加载...</Typography>
                  </Box>
                  <Typography variant="h4" sx={{ mt: 1 }}>
                    --
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
        
        <Typography variant="body1" sx={{ textAlign: 'center', color: 'text.secondary' }}>
          正在加载预测数据，可能需要几秒钟。
        </Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ p: 3 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h4" component="h1" gutterBottom>
          需求预测仪表板
        </Typography>
        <IconButton aria-label="刷新预测数据" onClick={() => {
          refetchDashboard();
        }} color="primary">
          <RefreshIcon />
        </IconButton>
      </Box>

      {/* XGBoost Integration Summary */}
      <Alert severity="success" sx={{ mb: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
          <Typography variant="h6" sx={{ fontWeight: 'bold', mr: 1 }}>
            🚀 XGBoost 集成已完成！
          </Typography>
          <Chip label="新" color="primary" size="small" />
        </Box>
        <Typography variant="body2">
          需求预测系统现已将 <strong>XGBoost</strong> 纳入高级集成模型。
          XGBoost 通过超参数优化提高预测准确度，并已与随机森林、梯度提升等模型协同生成预测。
        </Typography>
      </Alert>

      {/* Summary Cards */}
      <Grid container spacing={3} sx={{ mb: 3 }}>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                <AnalyticsIcon color="primary" sx={{ mr: 1 }} />
                <Typography variant="h6" component="div">
                  已预测产品
                </Typography>
              </Box>
              <Typography variant="h4" component="div" sx={{ mt: 1 }}>
                {(dashboardData as any)?.forecast_summary?.total_skus || 0}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                <WarningIcon color="warning" sx={{ mr: 1 }} />
                <Typography variant="h6" component="div">
                  补货警报
                </Typography>
              </Box>
              <Typography variant="h4" component="div" sx={{ mt: 1 }}>
                {(dashboardData as any)?.reorder_recommendations?.filter((r: any) => 
                  r.urgency_level === 'HIGH' || r.urgency_level === 'CRITICAL'
                ).length || 0}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                <SpeedIcon color="info" sx={{ mr: 1 }} />
                <Typography variant="h6" component="div">
                  平均准确率
                </Typography>
              </Box>
              <Typography variant="h4" component="div" sx={{ mt: 1 }}>
                {(dashboardData as any)?.model_performance ? 
                  `${((dashboardData as any).model_performance.reduce((acc: number, m: any) => acc + m.accuracy_score, 0) / (dashboardData as any).model_performance.length * 100).toFixed(1)}%` 
                  : '暂无'
                }
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                <InventoryIcon color="success" sx={{ mr: 1 }} />
                <Typography variant="h6" component="div">
                  活跃模型
                </Typography>
              </Box>
              <Typography variant="h4" component="div" sx={{ mt: 1 }}>
                {(dashboardData as any)?.model_performance?.length || 0}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Tabs */}
      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
        <Tabs value={selectedTab} onChange={handleTabChange} aria-label="预测功能标签页">
          <Tab label="预测摘要" />
          <Tab label="补货建议" />
          <Tab label="模型性能" />
          <Tab label="商业智能" />
          <Tab label="训练" />
        </Tabs>
      </Box>

      {/* Forecast Summary Tab */}
      <TabPanel value={selectedTab} index={0} idPrefix="forecast">
        <Typography variant="h5" gutterBottom>
          产品需求预测
        </Typography>
        <TableContainer component={Paper}>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>SKU</TableCell>
                <TableCell>平均日需求</TableCell>
                <TableCell>最低需求</TableCell>
                <TableCell>最高需求</TableCell>
                <TableCell>趋势</TableCell>
                <TableCell>预测日期</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(dashboardData as any)?.forecast_summary?.forecast_summary && Object.entries((dashboardData as any).forecast_summary.forecast_summary).map(([sku, data]: [string, any]) => (
                <TableRow key={sku}>
                  <TableCell>
                    <Typography variant="body2" fontWeight="bold">
                      {sku}
                    </Typography>
                  </TableCell>
                  <TableCell>{data.average_daily_demand.toFixed(1)}</TableCell>
                  <TableCell>{data.min_demand.toFixed(1)}</TableCell>
                  <TableCell>{data.max_demand.toFixed(1)}</TableCell>
                  <TableCell>
                    <Box sx={{ display: 'flex', alignItems: 'center' }}>
                      {getTrendIcon(data.trend)}
                      <Typography variant="body2" sx={{ ml: 1, textTransform: 'capitalize' }}>
                        {translateTrend(data.trend)}
                      </Typography>
                    </Box>
                  </TableCell>
                  <TableCell>
                    {formatZhDate(data.forecast_date)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </TabPanel>

      {/* Reorder Recommendations Tab */}
      <TabPanel value={selectedTab} index={1} idPrefix="forecast">
        <Typography variant="h5" gutterBottom>
          补货建议
        </Typography>
        {(dashboardData as any)?.reorder_recommendations && (dashboardData as any).reorder_recommendations.length > 0 ? (
          <TableContainer component={Paper}>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>SKU</TableCell>
                  <TableCell>当前库存</TableCell>
                  <TableCell>建议订货量</TableCell>
                  <TableCell>紧迫程度</TableCell>
                  <TableCell>原因</TableCell>
                  <TableCell>置信度</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {(dashboardData as any).reorder_recommendations.map((rec: any, index: number) => (
                  <TableRow key={index}>
                    <TableCell>
                      <Typography variant="body2" fontWeight="bold">
                        {rec.sku}
                      </Typography>
                    </TableCell>
                    <TableCell>{rec.current_stock}</TableCell>
                    <TableCell>{rec.recommended_order_quantity}</TableCell>
                    <TableCell>
                      <Chip 
                        label={translatePriority(rec.urgency_level)} 
                        color={getUrgencyColor(rec.urgency_level.toLowerCase()) as any}
                        size="small"
                      />
                    </TableCell>
                    <TableCell>{rec.reason}</TableCell>
                    <TableCell>{(rec.confidence_score * 100).toFixed(1)}%</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        ) : (
          <Alert severity="info">
            当前暂无补货建议。
          </Alert>
        )}
      </TabPanel>

      {/* Model Performance Tab */}
      <TabPanel value={selectedTab} index={2} idPrefix="forecast">
        <Typography variant="h5" gutterBottom>
          模型性能指标
        </Typography>
        
        {/* Model Comparison Cards */}
        <Grid container spacing={2} sx={{ mb: 3 }}>
          {(dashboardData as any)?.model_performance?.map((model: any, index: number) => (
            <Grid item xs={12} sm={6} md={4} key={index}>
              <Card sx={{ 
                border: model.model_name === 'XGBoost' ? '2px solid' : '1px solid',
                borderColor: model.model_name === 'XGBoost' ? 'primary.main' : 'divider',
                backgroundColor: 'background.paper'
              }}>
                <CardContent>
                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                    <Typography variant="h6" component="div" sx={{ 
                      fontWeight: 'bold',
                      color: model.model_name === 'XGBoost' ? 'primary.main' : 'text.primary'
                    }}>
                      {model.model_name}
                    </Typography>
                    {model.model_name === 'XGBoost' && (
                      <Chip 
                        label="新" 
                        size="small" 
                        color="primary" 
                        sx={{ ml: 1, fontSize: '0.7rem' }}
                      />
                    )}
                  </Box>
                  
                  <Box sx={{ mb: 2 }}>
                    <Typography variant="body2" color="text.secondary" gutterBottom>
                      准确率得分
                    </Typography>
                    <Box sx={{ display: 'flex', alignItems: 'center' }}>
                      <LinearProgress 
                        variant="determinate" 
                        value={model.accuracy_score * 100} 
                        color={getAccuracyColor(model.accuracy_score) as any}
                        sx={{ width: '100%', mr: 1, height: 8, borderRadius: 4 }}
                      />
                      <Typography variant="body2" fontWeight="bold">
                        {(model.accuracy_score * 100).toFixed(1)}%
                      </Typography>
                    </Box>
                  </Box>
                  
                  <Grid container spacing={1}>
                    <Grid item xs={6}>
                      <Typography variant="body2" color="text.secondary">
                        MAPE
                      </Typography>
                      <Typography variant="body2" fontWeight="bold">
                        {model.mape.toFixed(1)}%
                      </Typography>
                    </Grid>
                    <Grid item xs={6}>
                      <Typography variant="body2" color="text.secondary">
                        漂移得分
                      </Typography>
                      <Typography variant="body2" fontWeight="bold">
                        {model.drift_score.toFixed(2)}
                      </Typography>
                    </Grid>
                  </Grid>
                  
                  <Box sx={{ mt: 2, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <Chip
                      icon={model.status === 'HEALTHY' ? <CheckCircleIcon /> : <WarningIcon />}
                      label={translateModelStatus(model.status)}
                      color={model.status === 'HEALTHY' ? 'success' : model.status === 'WARNING' ? 'warning' : 'error'}
                      size="small"
                    />
                    <Typography variant="caption" color="text.secondary">
                      {formatZhDate(model.last_training_date)}
                    </Typography>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
        
        {/* Detailed Model Performance Table */}
        <Typography variant="h6" gutterBottom sx={{ mt: 3 }}>
          详细性能指标
        </Typography>
        {(dashboardData as any)?.model_performance && (dashboardData as any).model_performance.length > 0 ? (
          <TableContainer component={Paper}>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>模型名称</TableCell>
                  <TableCell>准确率</TableCell>
                  <TableCell>MAPE</TableCell>
                  <TableCell>漂移得分</TableCell>
                  <TableCell>预测数</TableCell>
                  <TableCell>最后训练</TableCell>
                  <TableCell>状态</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {(dashboardData as any).model_performance.map((model: any, index: number) => (
                  <TableRow key={index} sx={{ 
                    backgroundColor: model.model_name === 'XGBoost' ? 'background.paper' : 'inherit'
                  }}>
                    <TableCell>
                      <Box sx={{ display: 'flex', alignItems: 'center' }}>
                        <Typography variant="body2" fontWeight="bold">
                          {model.model_name}
                        </Typography>
                        {model.model_name === 'XGBoost' && (
                          <Chip 
                            label="新" 
                            size="small" 
                            color="primary" 
                            sx={{ ml: 1, fontSize: '0.7rem' }}
                          />
                        )}
                      </Box>
                    </TableCell>
                    <TableCell>
                      <Box sx={{ display: 'flex', alignItems: 'center' }}>
                        <LinearProgress 
                          variant="determinate" 
                          value={model.accuracy_score * 100} 
                          color={getAccuracyColor(model.accuracy_score) as any}
                          sx={{ width: 100, mr: 1 }}
                        />
                        <Typography variant="body2">
                          {(model.accuracy_score * 100).toFixed(1)}%
                        </Typography>
                      </Box>
                    </TableCell>
                    <TableCell>{model.mape.toFixed(1)}%</TableCell>
                    <TableCell>{model.drift_score.toFixed(2)}</TableCell>
                    <TableCell>
                      <Typography variant="body2">
                        {model.prediction_count.toLocaleString()}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      {formatZhDate(model.last_training_date)}
                    </TableCell>
                    <TableCell>
                      <Chip 
                        icon={model.status === 'HEALTHY' ? <CheckCircleIcon /> : <WarningIcon />}
                        label={translateModelStatus(model.status)} 
                        color={model.status === 'HEALTHY' ? 'success' : model.status === 'WARNING' ? 'warning' : 'error'}
                        size="small"
                      />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        ) : (
          <Alert severity="info">
            暂无模型性能数据。
          </Alert>
        )}
      </TabPanel>

      {/* Business Intelligence Tab */}
      <TabPanel value={selectedTab} index={3} idPrefix="forecast">
        <Typography variant="h5" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <AnalyticsIcon color="primary" />
          增强型商业智能仪表板
        </Typography>
        
        {(dashboardData as any)?.business_intelligence ? (
          <Box>
            {/* Key Performance Indicators */}
            <Grid container spacing={3} sx={{ mb: 3 }}>
              <Grid item xs={12} sm={6} md={3}>
                <Card sx={{ background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)', color: 'white' }}>
                  <CardContent>
                    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <Box>
                        <Typography variant="h4" fontWeight="bold">
                          {(dashboardData as any).business_intelligence.inventory_analytics?.total_skus || 0}
                        </Typography>
                        <Typography variant="body2" sx={{ opacity: 0.9 }}>
                          SKU 总数
                        </Typography>
                      </Box>
                      <InventoryIcon sx={{ fontSize: 40, opacity: 0.8 }} />
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
              
              <Grid item xs={12} sm={6} md={3}>
                <Card sx={{ background: 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)', color: 'white' }}>
                  <CardContent>
                    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <Box>
                        <Typography variant="h4" fontWeight="bold">
                          {(dashboardData as any).business_intelligence.inventory_analytics?.total_quantity?.toLocaleString() || '0'}
                        </Typography>
                        <Typography variant="body2" sx={{ opacity: 0.9 }}>
                          总数量
                        </Typography>
                      </Box>
                      <StorageIcon sx={{ fontSize: 40, opacity: 0.8 }} />
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
              
              <Grid item xs={12} sm={6} md={3}>
                <Card sx={{ background: 'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)', color: 'white' }}>
                  <CardContent>
                    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <Box>
                        <Typography variant="h4" fontWeight="bold">
                          {(dashboardData as any).business_intelligence.business_kpis?.forecast_coverage || 0}%
                        </Typography>
                        <Typography variant="body2" sx={{ opacity: 0.9 }}>
                          预测覆盖率
                        </Typography>
                      </Box>
                      <AssessmentIcon sx={{ fontSize: 40, opacity: 0.8 }} />
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
              
              <Grid item xs={12} sm={6} md={3}>
                <Card sx={{ background: 'linear-gradient(135deg, #43e97b 0%, #38f9d7 100%)', color: 'white' }}>
                  <CardContent>
                    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <Box>
                        <Typography variant="h4" fontWeight="bold">
                          {(dashboardData as any).business_intelligence.model_analytics?.avg_accuracy || 0}%
                        </Typography>
                        <Typography variant="body2" sx={{ opacity: 0.9 }}>
                          平均准确率
                        </Typography>
                      </Box>
                      <SpeedIcon sx={{ fontSize: 40, opacity: 0.8 }} />
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>

            {/* Risk Indicators */}
            <Grid container spacing={3} sx={{ mb: 3 }}>
              <Grid item xs={12} md={4}>
                <Card sx={{ border: '2px solid', borderColor: 'error.main' }}>
                  <CardContent>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
                      <WarningIcon color="error" />
                      <Typography variant="h6" color="error">
                        缺货风险
                      </Typography>
                    </Box>
                    <Typography variant="h3" color="error" fontWeight="bold">
                      {(dashboardData as any).business_intelligence.business_kpis?.stockout_risk || 0}%
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      有 {(dashboardData as any).business_intelligence.inventory_analytics?.low_stock_items || 0} 个产品低于补货点
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
              
              <Grid item xs={12} md={4}>
                <Card sx={{ border: '2px solid', borderColor: 'warning.main' }}>
                  <CardContent>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
                      <InfoIcon color="warning" />
                      <Typography variant="h6" color="warning.main">
                        库存过量警报
                      </Typography>
                    </Box>
                    <Typography variant="h3" color="warning.main" fontWeight="bold">
                      {(dashboardData as any).business_intelligence.business_kpis?.overstock_percentage || 0}%
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      有 {(dashboardData as any).business_intelligence.inventory_analytics?.overstock_items || 0} 个产品库存过量
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
              
              <Grid item xs={12} md={4}>
                <Card sx={{ border: '2px solid', borderColor: 'info.main' }}>
                  <CardContent>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
                      <TimelineIcon color="info" />
                      <Typography variant="h6" color="info.main">
                        需求波动性
                      </Typography>
                    </Box>
                    <Typography variant="h3" color="info.main" fontWeight="bold">
                      {(dashboardData as any).business_intelligence.business_kpis?.demand_volatility || 0}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      变异系数
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>

            {/* Category Performance */}
            <Grid container spacing={3} sx={{ mb: 3 }}>
              <Grid item xs={12} md={6}>
                <Card>
                  <CardContent>
                    <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <BarChartIcon color="primary" />
                      品类表现
                    </Typography>
                    <TableContainer>
                      <Table size="small">
                        <TableHead>
                          <TableRow>
                            <TableCell>品类</TableCell>
                            <TableCell align="right">SKUs</TableCell>
                            <TableCell align="right">数值</TableCell>
                            <TableCell align="right">低库存</TableCell>
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {(dashboardData as any).business_intelligence.category_analytics?.slice(0, 5).map((category: any) => (
                            <TableRow key={category.category}>
                              <TableCell>
                                <Chip 
                                  label={category.category} 
                                  size="small" 
                                  color="primary" 
                                  variant="outlined"
                                />
                              </TableCell>
                              <TableCell align="right">{category.sku_count}</TableCell>
                              <TableCell align="right">${category.category_quantity?.toLocaleString()}</TableCell>
                              <TableCell align="right">
                                <Chip 
                                  label={category.low_stock_count} 
                                  size="small" 
                                  color={category.low_stock_count > 0 ? 'error' : 'success'}
                                />
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </TableContainer>
                  </CardContent>
                </Card>
              </Grid>
              
              <Grid item xs={12} md={6}>
                <Card>
                  <CardContent>
                    <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <ShowChartIcon color="primary" />
                      预测趋势
                    </Typography>
                    {(dashboardData as any).business_intelligence.forecast_analytics ? (
                      <Box>
                        <Grid container spacing={2}>
                          <Grid item xs={4}>
                            <Box sx={{ textAlign: 'center', p: 2, bgcolor: 'success.light', borderRadius: 2 }}>
                              <ArrowUpwardIcon color="success" sx={{ fontSize: 30 }} />
                              <Typography variant="h4" color="success.dark" fontWeight="bold">
                                {(dashboardData as any).business_intelligence.forecast_analytics.trending_up}
                              </Typography>
                              <Typography variant="body2">上升趋势</Typography>
                            </Box>
                          </Grid>
                          <Grid item xs={4}>
                            <Box sx={{ textAlign: 'center', p: 2, bgcolor: 'error.light', borderRadius: 2 }}>
                              <ArrowDownwardIcon color="error" sx={{ fontSize: 30 }} />
                              <Typography variant="h4" color="error.dark" fontWeight="bold">
                                {(dashboardData as any).business_intelligence.forecast_analytics.trending_down}
                              </Typography>
                              <Typography variant="body2">下降趋势</Typography>
                            </Box>
                          </Grid>
                          <Grid item xs={4}>
                            <Box sx={{ textAlign: 'center', p: 2, bgcolor: 'info.light', borderRadius: 2 }}>
                              <RemoveIcon color="info" sx={{ fontSize: 30 }} />
                              <Typography variant="h4" color="info.dark" fontWeight="bold">
                                {(dashboardData as any).business_intelligence.forecast_analytics.stable_trends}
                              </Typography>
                              <Typography variant="body2">稳定</Typography>
                            </Box>
                          </Grid>
                        </Grid>
                        <Typography variant="body2" color="text.secondary" sx={{ mt: 2, textAlign: 'center' }}>
                          预测需求总量：{(dashboardData as any).business_intelligence.forecast_analytics.total_predicted_demand?.toLocaleString()}
                        </Typography>
                      </Box>
                    ) : (
                      <Typography variant="body2" color="text.secondary">
                        暂无预测分析数据
                      </Typography>
                    )}
                  </CardContent>
                </Card>
              </Grid>
            </Grid>

            {/* Top & Bottom Performers */}
            <Grid container spacing={3} sx={{ mb: 3 }}>
              <Grid item xs={12} md={6}>
                <Card>
                  <CardContent>
                    <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <StarIcon color="primary" />
                      表现最佳
                    </Typography>
                    <TableContainer>
                      <Table size="small">
                        <TableHead>
                          <TableRow>
                            <TableCell>SKU</TableCell>
                            <TableCell align="right">需求量</TableCell>
                            <TableCell align="right">日均需求</TableCell>
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {(dashboardData as any).business_intelligence.top_performers?.slice(0, 5).map((performer: any, index: number) => (
                            <TableRow key={performer.sku}>
                              <TableCell>
                                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                  <StarIcon color="primary" sx={{ fontSize: 16 }} />
                                  {performer.sku}
                                </Box>
                              </TableCell>
                              <TableCell align="right">{performer.total_demand?.toLocaleString()}</TableCell>
                              <TableCell align="right">{performer.avg_daily_demand?.toFixed(1)}</TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </TableContainer>
                  </CardContent>
                </Card>
              </Grid>
              
              <Grid item xs={12} md={6}>
                <Card>
                  <CardContent>
                    <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <StarBorderIcon color="secondary" />
                      表现最弱
                    </Typography>
                    <TableContainer>
                      <Table size="small">
                        <TableHead>
                          <TableRow>
                            <TableCell>SKU</TableCell>
                            <TableCell align="right">需求量</TableCell>
                            <TableCell align="right">日均需求</TableCell>
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {(dashboardData as any).business_intelligence.bottom_performers?.slice(0, 5).map((performer: any, index: number) => (
                            <TableRow key={performer.sku}>
                              <TableCell>
                                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                  <StarBorderIcon color="secondary" sx={{ fontSize: 16 }} />
                                  {performer.sku}
                                </Box>
                              </TableCell>
                              <TableCell align="right">{performer.total_demand?.toLocaleString()}</TableCell>
                              <TableCell align="right">{performer.avg_daily_demand?.toFixed(1)}</TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </TableContainer>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>

            {/* Recommendations */}
            <Card sx={{ mb: 3 }}>
              <CardContent>
                <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <InfoIcon color="primary" />
                  AI 建议
                </Typography>
                <Grid container spacing={2}>
                  {(dashboardData as any).business_intelligence.recommendations?.map((rec: any, index: number) => (
                    <Grid item xs={12} md={6} key={index}>
                      <Alert 
                        severity={rec.type === 'urgent' ? 'error' : rec.type === 'warning' ? 'warning' : 'info'}
                        sx={{ height: '100%' }}
                      >
                        <Typography variant="subtitle2" fontWeight="bold">
                          {rec.title}
                        </Typography>
                        <Typography variant="body2">
                          {rec.description}
                        </Typography>
                        <Typography variant="body2" sx={{ mt: 1, fontStyle: 'italic' }}>
                          💡 {rec.action}
                        </Typography>
                      </Alert>
                    </Grid>
                  ))}
                </Grid>
              </CardContent>
            </Card>

            {/* Model Performance Summary */}
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <MemoryIcon color="primary" />
                  模型性能分析
                </Typography>
                <Grid container spacing={3}>
                  <Grid item xs={12} md={3}>
                    <Box sx={{ textAlign: 'center', p: 2 }}>
                      <Typography variant="h4" color="primary" fontWeight="bold">
                        {(dashboardData as any).business_intelligence.model_analytics?.total_models || 0}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        活跃模型
                      </Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={12} md={3}>
                    <Box sx={{ textAlign: 'center', p: 2 }}>
                      <Typography variant="h4" color="success.main" fontWeight="bold">
                        {(dashboardData as any).business_intelligence.model_analytics?.models_above_80 || 0}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        高准确率（&gt;80%）
                      </Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={12} md={3}>
                    <Box sx={{ textAlign: 'center', p: 2 }}>
                      <Typography variant="h4" color="warning.main" fontWeight="bold">
                        {(dashboardData as any).business_intelligence.model_analytics?.models_below_70 || 0}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        低准确率（&lt;70%）
                      </Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={12} md={3}>
                    <Box sx={{ textAlign: 'center', p: 2 }}>
                      <Typography variant="h4" color="info.main" fontWeight="bold">
                        {(dashboardData as any).business_intelligence.model_analytics?.best_model || '暂无'}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        最佳模型
                      </Typography>
                    </Box>
                  </Grid>
                </Grid>
              </CardContent>
            </Card>
          </Box>
        ) : (
          <Alert severity="info">
            正在生成增强型商业智能数据...
          </Alert>
        )}
      </TabPanel>

      {/* Training Tab */}
      <TabPanel value={selectedTab} index={4} idPrefix="forecast">
        <Typography variant="h5" gutterBottom>
          模型训练与管理
        </Typography>
        
        {/* Training Controls */}
        <Grid container spacing={3} sx={{ mb: 3 }}>
          <Grid item xs={12} md={6}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  手动训练
                </Typography>
                <FormControl fullWidth sx={{ mb: 2 }}>
                  <InputLabel>训练类型</InputLabel>
                  <Select
                    value={trainingType}
                    label="训练类型"
                    onChange={(e) => setTrainingType(e.target.value as 'basic' | 'advanced')}
                  >
                    <MenuItem value="basic">基础（阶段 1 和 2）</MenuItem>
                    <MenuItem value="advanced">高级（阶段 3）</MenuItem>
                  </Select>
                </FormControl>
                <Box sx={{ display: 'flex', gap: 2 }}>
                  <Button
                    variant="contained"
                    startIcon={<PlayIcon />}
                    onClick={handleStartTraining}
                    disabled={(trainingStatus as any)?.is_running}
                    color="primary"
                  >
                    开始训练
                  </Button>
                  <Button
                    variant="outlined"
                    startIcon={<StopIcon />}
                    onClick={handleStopTraining}
                    disabled={!(trainingStatus as any)?.is_running}
                    color="error"
                  >
                    停止训练
                  </Button>
                </Box>
              </CardContent>
            </Card>
          </Grid>
          
          <Grid item xs={12} md={6}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  定时训练
                </Typography>
                <TextField
                  fullWidth
                  label="计划时间"
                  type="datetime-local"
                  value={scheduleTime}
                  onChange={(e) => setScheduleTime(e.target.value)}
                  InputLabelProps={{ shrink: true }}
                  sx={{ mb: 2 }}
                />
                <Button
                  variant="outlined"
                  startIcon={<ScheduleIcon />}
                  onClick={() => setScheduleDialogOpen(true)}
                  fullWidth
                >
                  计划训练
                </Button>
              </CardContent>
            </Card>
          </Grid>
        </Grid>

        {/* Training Status */}
        {trainingStatus && (
          <Card sx={{ mb: 3 }}>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                训练状态
              </Typography>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <Chip
                  icon={(trainingStatus as any).is_running ? <BuildIcon /> : <CheckCircleIcon />}
                  label={(trainingStatus as any).is_running ? '训练进行中' : '空闲'}
                  color={(trainingStatus as any).is_running ? 'primary' : 'default'}
                  sx={{ mr: 2 }}
                />
                {(trainingStatus as any).is_running && (
                  <Typography variant="body2" color="text.secondary">
                    {translateTrainingMessage((trainingStatus as any).current_step)}
                  </Typography>
                )}
              </Box>
              
              {(trainingStatus as any).is_running && (
                <Box sx={{ mb: 2 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                    <Typography variant="body2" sx={{ mr: 2 }}>
                      进度：{(trainingStatus as any).progress}%
                    </Typography>
                    {(trainingStatus as any).estimated_completion && (
                      <Typography variant="body2" color="text.secondary">
                        预计完成时间：{formatZhDateTime((trainingStatus as any).estimated_completion)}
                      </Typography>
                    )}
                  </Box>
                  <LinearProgress 
                    variant="determinate" 
                    value={(trainingStatus as any).progress} 
                    sx={{ height: 8, borderRadius: 4 }}
                  />
                </Box>
              )}
              
              {(trainingStatus as any).error && (
                <Alert severity="error" sx={{ mt: 2 }}>
                  {translateTrainingMessage((trainingStatus as any).error)}
                </Alert>
              )}
            </CardContent>
          </Card>
        )}

        {/* Training Logs */}
        {(trainingStatus as any)?.logs && (trainingStatus as any).logs.length > 0 && (
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                训练日志
              </Typography>
              <Box sx={{ 
                maxHeight: 300, 
                overflow: 'auto', 
                backgroundColor: 'background.default', 
                p: 2, 
                borderRadius: 1,
                fontFamily: 'monospace',
                fontSize: '0.875rem',
                border: '1px solid',
                borderColor: 'divider'
              }}>
                {(trainingStatus as any).logs.map((log: any, index: number) => (
                  <Typography key={index} variant="body2" sx={{ mb: 0.5 }}>
                    {translateTrainingMessage(log)}
                  </Typography>
                ))}
              </Box>
            </CardContent>
          </Card>
        )}

        {/* Training History */}
        {trainingHistory && (
          <Card sx={{ mt: 3 }}>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                训练历史
              </Typography>
              <TableContainer>
                <Table>
                  <TableHead>
                    <TableRow>
                      <TableCell>训练 ID</TableCell>
                      <TableCell>类型</TableCell>
                      <TableCell>开始时间</TableCell>
                      <TableCell>持续时间</TableCell>
                      <TableCell>状态</TableCell>
                      <TableCell>已训练模型</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {trainingHistory.training_sessions.map((session) => (
                      <TableRow key={session.id}>
                        <TableCell>{session.id}</TableCell>
                        <TableCell>
                          <Chip 
                            label={translateTrainingType(session.type)} 
                            size="small" 
                            color={session.type === 'advanced' ? 'primary' : 'default'}
                          />
                        </TableCell>
                        <TableCell>
                          {formatZhDateTime(session.start_time)}
                        </TableCell>
                        <TableCell>
                          {(() => {
                            // Use duration_seconds if available for more accurate display
                            if (session.duration_seconds !== undefined) {
                              const seconds = session.duration_seconds;
                              if (seconds < 60) {
                                return `${seconds} 秒`;
                              } else {
                                const mins = Math.floor(seconds / 60);
                                const secs = seconds % 60;
                                return secs > 0 ? `${mins} 分 ${secs} 秒` : `${mins} 分钟`;
                              }
                            }
                            // Fallback to duration_minutes
                            return session.duration_minutes > 0 
                              ? `${session.duration_minutes} 分钟` 
                              : '少于 1 分钟';
                          })()}
                        </TableCell>
                        <TableCell>
                          <Chip 
                            label={translateStatus(session.status)} 
                            size="small" 
                            color={session.status === 'completed' ? 'success' : 'default'}
                          />
                        </TableCell>
                        <TableCell>{session.models_trained}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </CardContent>
          </Card>
        )}
      </TabPanel>

      {/* Schedule Training Dialog */}
      <Dialog open={scheduleDialogOpen} onClose={() => setScheduleDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>计划训练</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            将{translateTrainingType(trainingType)}训练安排在指定时间，系统将在计划时间自动开始训练。
          </Typography>
          <TextField
            fullWidth
            label="计划时间"
            type="datetime-local"
            value={scheduleTime}
            onChange={(e) => setScheduleTime(e.target.value)}
            InputLabelProps={{ shrink: true }}
            sx={{ mb: 2 }}
          />
          <FormControl fullWidth>
            <InputLabel>训练类型</InputLabel>
            <Select
              value={trainingType}
              label="训练类型"
              onChange={(e) => setTrainingType(e.target.value as 'basic' | 'advanced')}
            >
              <MenuItem value="basic">基础（阶段 1 和 2）- 5–10 分钟</MenuItem>
              <MenuItem value="advanced">高级（阶段 3）- 10–20 分钟</MenuItem>
            </Select>
          </FormControl>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setScheduleDialogOpen(false)}>取消</Button>
          <Button 
            onClick={handleScheduleTraining} 
            variant="contained"
            disabled={!scheduleTime}
          >
            计划训练
          </Button>
        </DialogActions>
      </Dialog>

      {/* Training Progress Dialog */}
      <Dialog open={trainingDialogOpen} onClose={() => setTrainingDialogOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>训练进行中</DialogTitle>
        <DialogContent>
          {(trainingStatus as any)?.is_running ? (
            <Box>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <CircularProgress size={24} sx={{ mr: 2 }} />
                <Typography variant="h6">
                  {translateTrainingMessage((trainingStatus as any).current_step)}
                </Typography>
              </Box>
              <LinearProgress 
                variant="determinate" 
                value={(trainingStatus as any).progress} 
                sx={{ height: 8, borderRadius: 4, mb: 2 }}
              />
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                进度：{(trainingStatus as any).progress}%
                {(trainingStatus as any).estimated_completion && (
                  <> • 预计完成时间：{formatZhDateTime((trainingStatus as any).estimated_completion)}</>
                )}
              </Typography>
              <Box sx={{ 
                maxHeight: 200, 
                overflow: 'auto', 
                backgroundColor: 'background.default', 
                p: 2, 
                borderRadius: 1,
                fontFamily: 'monospace',
                border: '1px solid',
                borderColor: 'divider',
                fontSize: '0.875rem'
              }}>
                {(trainingStatus as any).logs.slice(-10).map((log: any, index: number) => (
                  <Typography key={index} variant="body2" sx={{ mb: 0.5 }}>
                    {translateTrainingMessage(log)}
                  </Typography>
                ))}
              </Box>
            </Box>
          ) : (
            <Box sx={{ textAlign: 'center', py: 4 }}>
              <CheckCircleIcon color="success" sx={{ fontSize: 48, mb: 2 }} />
              <Typography variant="h6" gutterBottom>
                训练已完成！
              </Typography>
              <Typography variant="body2" color="text.secondary">
                模型已成功训练，可以投入使用。
              </Typography>
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setTrainingDialogOpen(false)}>
            {(trainingStatus as any)?.is_running ? '最小化' : '关闭'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default ForecastingPage;

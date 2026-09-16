import React from 'react';
import {
  Box,
  Typography,
  Paper,
  Grid,
  Card,
  CardContent,
} from '@mui/material';
import {
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
} from 'recharts';
import { useQuery } from '@tanstack/react-query';
import { equipmentAPI, safetyAPI } from '../services/api';
import { translateAssetType, translateStatus } from '../localization/zhCN';

const Analytics: React.FC = () => {
  const { data: equipmentAssets } = useQuery({ queryKey: ['equipment'], queryFn: equipmentAPI.getAllAssets });
  const { data: incidents } = useQuery({ queryKey: ['incidents'], queryFn: safetyAPI.getIncidents });

  // Equipment assets data processing
  const equipmentTrendData = React.useMemo(() => {
    if (!equipmentAssets) return [];
    
    // Group equipment by type
    const equipmentByType = equipmentAssets.reduce((acc, asset) => {
      const type = asset.type || '未知';
      if (!acc[type]) {
        acc[type] = 0;
      }
      acc[type]++;
      return acc;
    }, {} as Record<string, number>);

    // Convert to chart data format
    return Object.entries(equipmentByType).map(([type, count]) => ({
      type,
      count,
      percentage: ((count / equipmentAssets.length) * 100).toFixed(1)
    }));
  }, [equipmentAssets]);

  // Equipment status distribution
  const equipmentStatusData = React.useMemo(() => {
    if (!equipmentAssets) return [];
    
    const statusCounts = equipmentAssets.reduce((acc, asset) => {
      const status = asset.status || '未知';
      if (!acc[status]) {
        acc[status] = 0;
      }
      acc[status]++;
      return acc;
    }, {} as Record<string, number>);

    return Object.entries(statusCounts).map(([status, count]) => ({
      status,
      count,
      percentage: ((count / equipmentAssets.length) * 100).toFixed(1)
    }));
  }, [equipmentAssets]);


  const incidentSeverityData = [
    { severity: '低', count: incidents?.filter(i => i.severity === 'low').length || 0 },
    { severity: '中', count: incidents?.filter(i => i.severity === 'medium').length || 0 },
    { severity: '高', count: incidents?.filter(i => i.severity === 'high').length || 0 },
    { severity: '严重', count: incidents?.filter(i => i.severity === 'critical').length || 0 },
  ];

  const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042'];

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        分析仪表板
      </Typography>

      <Grid container spacing={3}>
        {/* Equipment Assets by Type */}
        <Grid item xs={12} md={8}>
          <Paper sx={{ p: 2 }}>
            <Typography variant="h6" gutterBottom>
              按类型统计设备资产
            </Typography>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={equipmentTrendData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="type" tickFormatter={(value) => translateAssetType(value)} />
                <YAxis />
                <Tooltip 
                  formatter={(value) => [value, '数量']}
                  labelFormatter={(label) => `类型：${translateAssetType(label)}`}
                />
                <Legend />
                <Bar dataKey="count" fill="#8884d8" name="设备数量" />
              </BarChart>
            </ResponsiveContainer>
          </Paper>
        </Grid>

        {/* Equipment Status Distribution */}
        <Grid item xs={12} md={4}>
          <Paper sx={{ p: 2 }}>
            <Typography variant="h6" gutterBottom>
              设备状态
            </Typography>
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie
                  data={equipmentStatusData}
                  cx="50%"
                  cy="50%"
                  labelLine={false}
                  label={({ status, percent }) => `${translateStatus(status)} ${(percent * 100).toFixed(0)}%`}
                  outerRadius={80}
                  fill="#8884d8"
                  dataKey="count"
                >
                  {equipmentStatusData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip
                  formatter={(value) => [value, '数量']}
                  labelFormatter={(label) => translateStatus(String(label))}
                />
              </PieChart>
            </ResponsiveContainer>
          </Paper>
        </Grid>

        {/* Equipment Type Breakdown */}
        <Grid item xs={12} md={6}>
          <Paper sx={{ p: 2 }}>
            <Typography variant="h6" gutterBottom>
              设备类型分布
            </Typography>
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie
                  data={equipmentTrendData}
                  cx="50%"
                  cy="50%"
                  labelLine={false}
                  label={({ type, percent }) => `${translateAssetType(type)} ${(percent * 100).toFixed(0)}%`}
                  outerRadius={80}
                  fill="#8884d8"
                  dataKey="count"
                >
                  {equipmentTrendData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip
                  formatter={(value) => [value, '数量']}
                  labelFormatter={(label) => translateAssetType(String(label))}
                />
              </PieChart>
            </ResponsiveContainer>
          </Paper>
        </Grid>

        {/* Incident Severity */}
        <Grid item xs={12} md={6}>
          <Paper sx={{ p: 2 }}>
            <Typography variant="h6" gutterBottom>
              安全事件严重程度分布
            </Typography>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={incidentSeverityData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="severity" />
                <YAxis />
                <Tooltip formatter={(value) => [value, '事件数量']} />
                <Bar dataKey="count" fill="#8884d8" name="事件数量" />
              </BarChart>
            </ResponsiveContainer>
          </Paper>
        </Grid>

        {/* Equipment Key Metrics */}
        <Grid item xs={12} md={6}>
          <Paper sx={{ p: 2 }}>
            <Typography variant="h6" gutterBottom>
              设备关键指标
            </Typography>
            <Grid container spacing={2}>
              <Grid item xs={6}>
                <Card>
                  <CardContent>
                    <Typography color="textSecondary" gutterBottom>
                      设备资产总数
                    </Typography>
                    <Typography variant="h4">
                      {equipmentAssets?.length || 0}
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={6}>
                <Card>
                  <CardContent>
                    <Typography color="textSecondary" gutterBottom>
                      可用设备
                    </Typography>
                    <Typography variant="h4">
                      {equipmentAssets?.filter(asset => asset.status === 'available').length || 0}
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={6}>
                <Card>
                  <CardContent>
                    <Typography color="textSecondary" gutterBottom>
                      已分配设备
                    </Typography>
                    <Typography variant="h4">
                      {equipmentAssets?.filter(asset => asset.status === 'assigned').length || 0}
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={6}>
                <Card>
                  <CardContent>
                    <Typography color="textSecondary" gutterBottom>
                      需要维护
                    </Typography>
                    <Typography variant="h4">
                      {equipmentAssets?.filter(asset => 
                        asset.status === 'maintenance' || 
                        (asset.next_pm_due && new Date(asset.next_pm_due) <= new Date())
                      ).length || 0}
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          </Paper>
        </Grid>
      </Grid>
    </Box>
  );
};

export default Analytics;

import React, { useState } from 'react';
import {
  Box,
  Typography,
  Paper,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Grid,
  Chip,
  Alert,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
} from '@mui/material';
import { DataGrid, GridColDef } from '@mui/x-data-grid';
import { zhCN as dataGridZhCN } from '@mui/x-data-grid/locales';
import { } from '@mui/icons-material';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { operationsAPI, Task, userAPI, User } from '../services/api';
import { useDialogForm } from '../components/common';
import {
  formatZhDate,
  translateRole,
  translateStatus,
  translateTaskKind,
} from '../localization/zhCN';

const Operations: React.FC = () => {
  const {
    open,
    setOpen,
    selectedItem: selectedTask,
    setSelectedItem: setSelectedTask,
    formData,
    setFormData,
    handleOpen,
    handleClose,
  } = useDialogForm<Task>();
  const queryClient = useQueryClient();

  const { data: tasks, isLoading, error } = useQuery({
    queryKey: ['tasks'],
    queryFn: operationsAPI.getTasks
  });

  const { data: workforceStatus } = useQuery({
    queryKey: ['workforce'],
    queryFn: operationsAPI.getWorkforceStatus
  });

  const { data: users } = useQuery({
    queryKey: ['users'],
    queryFn: userAPI.getUsers
  });

  const assignMutation = useMutation({
    mutationFn: ({ taskId, assignee }: { taskId: number; assignee: string }) =>
      operationsAPI.assignTask(taskId, assignee),
      onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] });
        handleClose();
    }
  });

  const handleSubmit = () => {
    if (selectedTask && formData.assignee) {
      assignMutation.mutate({ taskId: selectedTask.id, assignee: formData.assignee });
    }
  };

  const columns: GridColDef[] = [
    { field: 'id', headerName: 'ID', width: 80 },
    {
      field: 'kind',
      headerName: '任务类型',
      width: 150,
      renderCell: (params) => translateTaskKind(params.value),
    },
    {
      field: 'status',
      headerName: '状态',
      width: 120,
      renderCell: (params) => {
        const status = params.value;
        const color = status === 'completed' ? 'success' : 
                     status === 'in_progress' ? 'info' : 'warning';
        return <Chip label={translateStatus(status)} color={color} size="small" />;
      },
    },
    { field: 'assignee', headerName: '负责人', width: 150 },
    {
      field: 'created_at',
      headerName: '创建日期',
      width: 150,
      renderCell: (params) => formatZhDate(params.value),
    },
    {
      field: 'actions',
      headerName: '操作',
      width: 120,
      renderCell: (params) => (
        <Button
          size="small"
          onClick={() => handleOpen(params.row)}
        >
          分配
        </Button>
      ),
    },
  ];

  if (error) {
    return (
      <Box>
        <Typography variant="h4" gutterBottom>
          运营管理
        </Typography>
        <Alert severity="error">
          运营数据加载失败，请重试。
        </Alert>
      </Box>
    );
  }

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        运营管理
      </Typography>

      {/* Workforce Status */}
      {workforceStatus && (
        <Paper sx={{ p: 3, mb: 3 }}>
          <Typography variant="h6" gutterBottom>
            人力状态
          </Typography>
          <Grid container spacing={3}>
            <Grid item xs={12} sm={6} md={3}>
              <Box sx={{ 
                p: 2, 
                border: 1, 
                borderColor: 'divider', 
                borderRadius: 2,
                textAlign: 'center',
                backgroundColor: 'primary.light',
                color: 'primary.contrastText'
              }}>
                <Typography variant="h4" sx={{ fontWeight: 'bold' }}>
                  {workforceStatus.total_workers}
                </Typography>
                <Typography variant="body2">
                  员工总数
                </Typography>
              </Box>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Box sx={{ 
                p: 2, 
                border: 1, 
                borderColor: 'divider', 
                borderRadius: 2,
                textAlign: 'center',
                backgroundColor: 'success.light',
                color: 'success.contrastText'
              }}>
                <Typography variant="h4" sx={{ fontWeight: 'bold' }}>
                  {workforceStatus.active_workers}
                </Typography>
                <Typography variant="body2">
                  活跃员工
                </Typography>
              </Box>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Box sx={{ 
                p: 2, 
                border: 1, 
                borderColor: 'divider', 
                borderRadius: 2,
                textAlign: 'center',
                backgroundColor: 'info.light',
                color: 'info.contrastText'
              }}>
                <Typography variant="h4" sx={{ fontWeight: 'bold' }}>
                  {workforceStatus.available_workers}
                </Typography>
                <Typography variant="body2">
                  可用员工
                </Typography>
              </Box>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Box sx={{ 
                p: 2, 
                border: 1, 
                borderColor: 'divider', 
                borderRadius: 2,
                textAlign: 'center',
                backgroundColor: 'warning.light',
                color: 'warning.contrastText'
              }}>
                <Typography variant="h4" sx={{ fontWeight: 'bold' }}>
                  {workforceStatus.tasks_in_progress}
                </Typography>
                <Typography variant="body2">
                  进行中任务
                </Typography>
              </Box>
            </Grid>
            <Grid item xs={12} sm={6} md={6}>
              <Box sx={{ 
                p: 2, 
                border: 1, 
                borderColor: 'divider', 
                borderRadius: 2,
                textAlign: 'center',
                backgroundColor: 'secondary.light',
                color: 'secondary.contrastText'
              }}>
                <Typography variant="h4" sx={{ fontWeight: 'bold' }}>
                  {workforceStatus.tasks_pending}
                </Typography>
                <Typography variant="body2">
                  待处理任务
                </Typography>
              </Box>
            </Grid>
            <Grid item xs={12} sm={6} md={6}>
              <Box sx={{ 
                p: 2, 
                border: 1, 
                borderColor: 'divider', 
                borderRadius: 2,
                textAlign: 'center',
                backgroundColor: 'grey.200',
                color: 'text.primary'
              }}>
                <Typography variant="h4" sx={{ fontWeight: 'bold' }}>
                  {Math.round((workforceStatus.active_workers / workforceStatus.total_workers) * 100)}%
                </Typography>
                <Typography variant="body2">
                  人力利用率
                </Typography>
              </Box>
            </Grid>
          </Grid>
        </Paper>
      )}

      {/* Tasks Management */}
      <Paper sx={{ height: 600, width: '100%' }}>
        <DataGrid
          rows={tasks || []}
          columns={columns}
          localeText={dataGridZhCN.components.MuiDataGrid.defaultProps.localeText}
          loading={isLoading}
          initialState={{
            pagination: {
              paginationModel: { pageSize: 10 },
            },
          }}
          pageSizeOptions={[10, 25, 50]}
          disableRowSelectionOnClick
        />
      </Paper>

      <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
        <DialogTitle>
          {selectedTask ? '分配任务' : '创建新任务'}
        </DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="任务类型"
                value={formData.kind || ''}
                onChange={(e) => setFormData({ ...formData, kind: e.target.value })}
                disabled={!!selectedTask}
                required
              />
            </Grid>
            <Grid item xs={12}>
              <FormControl fullWidth>
                <InputLabel>负责人</InputLabel>
                <Select
                  value={formData.assignee || ''}
                  onChange={(e) => setFormData({ ...formData, assignee: e.target.value })}
                  label="负责人"
                >
                  {users && users.length > 0 ? (
                    users.map((user: User) => (
                      <MenuItem key={user.id} value={user.full_name || user.username}>
                        {user.full_name || user.username}（{translateRole(user.role)}）
                      </MenuItem>
                    ))
                  ) : (
                    <MenuItem value="">暂无可用用户</MenuItem>
                  )}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12}>
              <FormControl fullWidth>
                <InputLabel>状态</InputLabel>
                <Select
                  value={formData.status || ''}
                  onChange={(e) => setFormData({ ...formData, status: e.target.value })}
                  label="状态"
                >
                  <MenuItem value="pending">待处理</MenuItem>
                  <MenuItem value="in_progress">进行中</MenuItem>
                  <MenuItem value="completed">已完成</MenuItem>
                </Select>
              </FormControl>
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleClose}>取消</Button>
          <Button
            onClick={handleSubmit}
            variant="contained"
            disabled={assignMutation.isPending}
          >
            {selectedTask ? '分配' : '创建'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default Operations;

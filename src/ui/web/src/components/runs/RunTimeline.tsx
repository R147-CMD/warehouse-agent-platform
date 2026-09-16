import React from 'react';
import {
  Box,
  Chip,
  List,
  ListItem,
  ListItemText,
  Stack,
  Typography,
} from '@mui/material';
import { AgentRunEvent } from '../../services/api';

interface RunTimelineProps {
  events: AgentRunEvent[];
}

const severityColor: Record<AgentRunEvent['severity'], 'default' | 'warning' | 'error' | 'info' | 'success'> = {
  info: 'info',
  warning: 'warning',
  error: 'error',
};

const eventTypeLabel: Record<string, string> = {
  'run.created': '任务创建',
  'run.started': '开始执行',
  'plan.created': '自主规划',
  'route.selected': '智能路由',
  'multi_agent.selected': '多智能体协作',
  'evidence.joined': '证据汇总',
  'agent.started': '智能体开始',
  'agent.completed': '智能体完成',
  'reflection.reviewed': '反思通过',
  'reflection.replan': '反思重规划',
  'reflection.clarification_requested': '反思追问',
  'tool.started': '工具开始',
  'tool.completed': '工具完成',
  'approval.requested': '请求审批',
  'approval.approved': '审批通过',
  'approval.rejected': '审批拒绝',
  'approval.expired': '审批过期',
  'checkpoint.saved': '检查点保存',
  'run.waiting_approval': '等待审批',
  'run.cancel_requested': '请求取消',
  'run.cancelled': '任务取消',
  'run.retry_requested': '请求重试',
  'run.completed': '任务完成',
  'run.failed': '任务失败',
};

const reflectionActionLabel: Record<string, string> = {
  finalize: '进入汇总',
  replan: '重新规划',
  clarify: '补充信息',
};

const judgeStatusLabel: Record<string, string> = {
  ok: 'LLM 评审',
  disabled: '规则评审',
  skipped: '规则兜底',
  fallback: '规则兜底',
};

const formatDateTime = (value: string) => {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? '未知时间'
    : date.toLocaleString('zh-CN', { hour12: false });
};

const getPayloadText = (payload: Record<string, unknown>, key: string) => {
  const value = payload[key];
  return typeof value === 'string' ? value : undefined;
};

const getPayloadNumber = (payload: Record<string, unknown>, key: string) => {
  const value = payload[key];
  return typeof value === 'number' ? value : undefined;
};

const getPayloadList = (payload: Record<string, unknown>, key: string) => {
  const value = payload[key];
  return Array.isArray(value)
    ? value.map((item) => String(item)).filter(Boolean)
    : [];
};

const getReflectionActionLabel = (payload: Record<string, unknown>) => {
  const action = getPayloadText(payload, 'action');
  return action ? reflectionActionLabel[action] || action : undefined;
};

const formatScore = (payload: Record<string, unknown>, key: string) => {
  const value = getPayloadNumber(payload, key);
  return value === undefined ? undefined : `${Math.round(value * 100)}分`;
};

const RunTimeline: React.FC<RunTimelineProps> = ({ events }) => {
  if (events.length === 0) {
    return (
      <Typography variant="body2" sx={{ color: 'text.secondary', py: 2 }}>
        暂无事件
      </Typography>
    );
  }

  return (
    <List dense disablePadding>
      {events.map((event) => (
        <ListItem
          key={event.event_id}
          alignItems="flex-start"
          sx={{
            px: 0,
            py: 1.25,
            borderBottom: '1px solid',
            borderColor: 'divider',
          }}
        >
          <ListItemText
            primary={
              <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
                <Typography variant="body2" sx={{ fontWeight: 600 }}>
                  {event.message}
                </Typography>
                <Chip
                  size="small"
                  color={severityColor[event.severity]}
                  label={eventTypeLabel[event.event_type] || event.event_type}
                  sx={{ height: 20, fontSize: '11px' }}
                />
              </Stack>
            }
            secondary={
              <Box sx={{ mt: 0.5 }}>
                <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                  {formatDateTime(event.created_at)}
                </Typography>
                <Stack direction="row" spacing={1} flexWrap="wrap" sx={{ mt: 0.75 }}>
                  {event.agent_name && <Chip size="small" label={`智能体：${event.agent_name}`} />}
                  {event.tool_name && <Chip size="small" label={`工具：${event.tool_name}`} />}
                  {event.approval_id && <Chip size="small" label={`审批：${event.approval_id}`} />}
                  {event.checkpoint_id && <Chip size="small" label={`检查点：${event.checkpoint_id}`} />}
                  {getPayloadList(event.payload, 'selected_agents').length > 0 && (
                    <Chip
                      size="small"
                      color="secondary"
                      variant="outlined"
                      label={`协作智能体：${getPayloadList(event.payload, 'selected_agents').join('、')}`}
                    />
                  )}
                  {getPayloadList(event.payload, 'contributing_agents').length > 0 && (
                    <Chip
                      size="small"
                      color="success"
                      variant="outlined"
                      label={`证据来源：${getPayloadList(event.payload, 'contributing_agents').join('、')}`}
                    />
                  )}
                  {getPayloadNumber(event.payload, 'evidence_count') !== undefined && (
                    <Chip
                      size="small"
                      label={`证据数：${getPayloadNumber(event.payload, 'evidence_count')}`}
                    />
                  )}
                  {getPayloadNumber(event.payload, 'average_confidence') !== undefined && (
                    <Chip
                      size="small"
                      label={`平均置信度：${Math.round((getPayloadNumber(event.payload, 'average_confidence') || 0) * 100)}分`}
                    />
                  )}
                  {getPayloadText(event.payload, 'action') && (
                    <Chip
                      size="small"
                      color="primary"
                      variant="outlined"
                      label={`反思动作：${getReflectionActionLabel(event.payload)}`}
                    />
                  )}
                  {getPayloadText(event.payload, 'route') && (
                    <Chip size="small" label={`当前路由：${getPayloadText(event.payload, 'route')}`} />
                  )}
                  {getPayloadText(event.payload, 'next_route') && (
                    <Chip size="small" label={`下一路由：${getPayloadText(event.payload, 'next_route')}`} />
                  )}
                  {getPayloadNumber(event.payload, 'iteration') !== undefined && (
                    <Chip
                      size="small"
                      label={`反思轮次：${getPayloadNumber(event.payload, 'iteration')}/${getPayloadNumber(event.payload, 'max_iterations') ?? '-'}`}
                    />
                  )}
                  {getPayloadText(event.payload, 'judge_status') && (
                    <Chip
                      size="small"
                      color={getPayloadText(event.payload, 'judge_status') === 'ok' ? 'success' : 'default'}
                      variant="outlined"
                      label={judgeStatusLabel[getPayloadText(event.payload, 'judge_status') || ''] || getPayloadText(event.payload, 'judge_status')}
                    />
                  )}
                  {formatScore(event.payload, 'quality_score') && (
                    <Chip size="small" label={`质量：${formatScore(event.payload, 'quality_score')}`} />
                  )}
                  {formatScore(event.payload, 'route_score') && (
                    <Chip size="small" label={`路由：${formatScore(event.payload, 'route_score')}`} />
                  )}
                  {formatScore(event.payload, 'safety_score') && (
                    <Chip size="small" label={`安全：${formatScore(event.payload, 'safety_score')}`} />
                  )}
                </Stack>
                {getPayloadList(event.payload, 'reasons').length > 0 && (
                  <Stack direction="row" spacing={1} flexWrap="wrap" sx={{ mt: 0.75 }}>
                    {getPayloadList(event.payload, 'reasons').slice(0, 3).map((reason) => (
                      <Chip key={reason} size="small" variant="outlined" label={`原因：${reason}`} />
                    ))}
                  </Stack>
                )}
                {getPayloadList(event.payload, 'gaps').length > 0 && (
                  <Stack direction="row" spacing={1} flexWrap="wrap" sx={{ mt: 0.75 }}>
                    {getPayloadList(event.payload, 'gaps').slice(0, 3).map((gap) => (
                      <Chip key={gap} size="small" color="warning" variant="outlined" label={`证据缺口：${gap}`} />
                    ))}
                  </Stack>
                )}
              </Box>
            }
          />
        </ListItem>
      ))}
    </List>
  );
};

export default RunTimeline;

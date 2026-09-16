import React, { useState, useRef, useEffect } from 'react';
import {
  Box,
  TextField,
  IconButton,
  Typography,
  Paper,
  Fab,
  Skeleton,
  Alert,
  Snackbar,
  Switch,
  FormControlLabel,
  FormGroup,
  Checkbox,
  Collapse,
  Chip,
  Tooltip,
} from '@mui/material';
import {
  Send as SendIcon,
  Menu as MenuIcon,
  Close as CloseIcon,
  Visibility as VisibilityIcon,
  VisibilityOff as VisibilityOffIcon,
  Psychology as PsychologyIcon,
  ExpandMore as ExpandMoreIcon,
  ExpandLess as ExpandLessIcon,
} from '@mui/icons-material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  approvalAPI,
  ApprovalDecisionResponse,
  ApprovalStatus,
  chatAPI,
  ChatResponse,
  healthAPI,
  operationsAPI,
  PendingApproval,
  ReasoningChain,
  ReasoningStep,
} from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import TopBar from '../components/chat/TopBar';
import LeftRail from '../components/chat/LeftRail';
import MessageBubble from '../components/chat/MessageBubble';
import ApprovalQueue from '../components/chat/ApprovalQueue';
import RightPanel from '../components/chat/RightPanel';
import { translateTaskKind } from '../localization/zhCN';
import { getOrCreateChatSessionId, rotateChatSessionId } from '../utils/chatSession';

interface Message {
  id: string;
  type: 'answer' | 'clarifying_question' | 'proposed_action' | 'action_result' | 'evidence' | 'notice' | 'warning' | 'error';
  content: string;
  sender: 'user' | 'assistant';
  timestamp: Date;
  route?: string;
  run_id?: string | null;
  confidence?: number;
  structured_data?: any;
  proposals?: PendingApproval[];
  execution_status?: string;
  clarifying?: {
    text: string;
    options: string[];
  };
  evidence?: Array<{
    type: 'sql' | 'doc';
    table?: string;
    rows?: number;
    lat_ms?: number;
    id?: string;
    score?: number;
  }>;
  reasoning_chain?: ReasoningChain;
  reasoning_steps?: ReasoningStep[];
}

interface StreamingEvent {
  stage: string;
  agent?: string;
  confidence?: number;
  k?: number;
  reranked?: number;
  evidence_score?: number;
  query?: string;
  lat_ms?: number;
  action?: string;
  approval_id?: string;
  text?: string;
  options?: string[];
}

interface ChatUiResponse extends ChatResponse {
  clarifying?: Message['clarifying'];
  evidence?: Message['evidence'];
  sql_query?: any;
  planner_decision?: any;
  tool_timeline?: any[];
}

const getApprovalStatusLabel = (status: ApprovalStatus) => {
  const labels: Record<ApprovalStatus, string> = {
    pending: '待审批',
    approved: '已批准',
    executing: '执行中',
    executed: '已执行',
    rejected: '已拒绝',
    expired: '已过期',
    failed: '执行失败',
  };
  return labels[status];
};

const getApprovalErrorMessage = (error: any) => {
  const status = error?.response?.status;
  if (status === 403) return '您没有审批该操作的权限。';
  if (status === 404) return '审批请求不存在或已失效。';
  if (status === 409) return '审批状态已发生变化，请刷新后重试。';
  if (status === 422) return '审批请求无效。';
  if (!error?.response) return '无法连接审批服务，请稍后重试。';
  return '审批处理失败，请稍后重试。';
};

const createWelcomeMessage = (): Message => ({
  id: `welcome-${Date.now()}`,
  type: 'answer',
  content: '您好！我是您的多智能体智能仓库助手。今天有什么可以帮您？',
  sender: 'assistant',
  timestamp: new Date(),
  route: 'general',
  confidence: 0.95,
});

const ChatInterfaceNew: React.FC = () => {
  const { isAuthenticated, user } = useAuth();
  const canApprove = user?.role === 'manager' || user?.role === 'admin';
  const queryClient = useQueryClient();
  const [sessionId, setSessionId] = useState(getOrCreateChatSessionId);
  const [messages, setMessages] = useState<Message[]>(() => [createWelcomeMessage()]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [rightPanelOpen, setRightPanelOpen] = useState(false);
  const [showInternals, setShowInternals] = useState(false);
  const [streamingEvents, setStreamingEvents] = useState<StreamingEvent[]>([]);
  const [currentEvidence, setCurrentEvidence] = useState<any[]>([]);
  const [currentSqlQuery, setCurrentSqlQuery] = useState<any>(null);
  const [currentPlannerDecision, setCurrentPlannerDecision] = useState<any>(null);
  const [currentActiveContext, setCurrentActiveContext] = useState<any>(null);
  const [currentToolTimeline, setCurrentToolTimeline] = useState<any[]>([]);
  const [currentReasoningChain, setCurrentReasoningChain] = useState<ReasoningChain | undefined>(undefined);
  const [currentReasoningSteps, setCurrentReasoningSteps] = useState<ReasoningStep[] | undefined>(undefined);
  const [busyApprovalIds, setBusyApprovalIds] = useState<Set<string>>(() => new Set());
  const [snackbar, setSnackbar] = useState<{ open: boolean; message: string; severity: 'success' | 'error' | 'info' }>({
    open: false,
    message: '',
    severity: 'info',
  });
  
  // Reasoning state
  const [enableReasoning, setEnableReasoning] = useState(false);
  const [showReasoningTypes, setShowReasoningTypes] = useState(false);
  const [selectedReasoningTypes, setSelectedReasoningTypes] = useState<string[]>([]);
  
  const availableReasoningTypes = [
    { value: 'chain_of_thought', label: '思维链', description: '逐步进行逻辑推理' },
    { value: 'multi_hop', label: '多跳推理', description: '跨多个数据点进行推理' },
    { value: 'scenario_analysis', label: '情景分析', description: '分析假设情景与替代方案' },
    { value: 'causal', label: '因果推理', description: '分析因果关系' },
    { value: 'pattern_recognition', label: '模式识别', description: '识别趋势和模式' },
  ];

  // Top bar state - use environment/config values
  const [warehouse, setWarehouse] = useState(process.env.REACT_APP_WAREHOUSE_ID || 'WH-01');
  const [environment, setEnvironment] = useState(process.env.NODE_ENV === 'production' ? 'Prod' : 'Dev');
  
  // This selector is business context for warehouse scenarios only. Authorization
  // always comes from the authenticated user and remains server-authoritative.
  const [businessRole, setBusinessRole] = useState('operator');
  
  // Connection status - check health endpoints
  const { data: healthStatus } = useQuery({
    queryKey: ['health'],
    queryFn: healthAPI.check,
    refetchInterval: 30000, // Check every 30 seconds
    retry: false,
    // Don't fail the query if health check is slow - it's non-critical
    refetchOnWindowFocus: false,
    staleTime: 60000, // Consider health status fresh for 60 seconds
    throwOnError: false, // Don't throw errors - handle them in onError
  });
  
  // Update connections based on health status
  const connections = {
    nim: true, // NVIDIA NIM - assume available if we're using it
    db: healthStatus?.ok || false,
    milvus: true, // Milvus health could be checked separately
    kafka: true, // Kafka health could be checked separately
  };

  // Recent tasks - get from actual API
  const { data: tasks } = useQuery({
    queryKey: ['recent-tasks'],
    queryFn: () => 
    operationsAPI.getTasks().then(tasks => 
      tasks?.slice(0, 5).map(task => {
        // Map task status to LeftRail expected status values
        let status: 'completed' | 'pending' | 'failed' = 'pending';
        if (task.status === 'completed') {
          status = 'completed';
        } else if (task.status === 'failed' || task.status === 'error') {
          status = 'failed';
        } else {
          // 'pending' or 'in_progress' both map to 'pending'
          status = 'pending';
        }
        
        return {
          id: String(task.id),
          title: `${translateTaskKind(task.kind)} - ${task.assignee || '未分配'}`,
          status,
          timestamp: new Date(task.created_at),
        };
      }) || []
    ),
    refetchInterval: 60000, // Refresh every minute
    retry: 1, // Retry once on failure
    refetchOnWindowFocus: false, // Don't refetch on window focus
    staleTime: 60000, // Consider data fresh for 60 seconds
    throwOnError: false, // Don't throw errors - handle them in component
  });
  
  const recentTasks = tasks || [];

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const sessionIdRef = useRef(sessionId);
  const streamIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const busyApprovalIdsRef = useRef<Set<string>>(new Set());

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => () => {
    if (streamIntervalRef.current) {
      clearInterval(streamIntervalRef.current);
    }
  }, []);

  const chatMutation = useMutation({
    mutationFn: chatAPI.sendMessage,
    onSuccess: (response, request) => {
      if (request.session_id !== sessionIdRef.current) {
        return;
      }

      console.log('Chat response received:', response);
      // Add message immediately so user sees it right away
      try {
        simulateStreamingResponse(response);
      } catch (error) {
        console.error('Error processing response:', error);
        // Fallback: add message directly if streaming fails
        const fallbackMessage: Message = {
          id: Date.now().toString(),
          type: 'answer',
          content: response.reply || '已收到响应，但无法显示',
          sender: 'assistant',
          timestamp: new Date(),
          route: response.route || 'general',
          run_id: response.run_id,
          confidence: response.confidence || 0.75,
        };
        setMessages(prev => [...prev, fallbackMessage]);
      }
    },
    onError: (error: any) => {
      console.error('Chat error:', error);
      // Handle network errors more gracefully
      let errorMessage = '消息发送失败';
      if (error.code === 'ECONNABORTED' || error.message?.includes('timeout')) {
        errorMessage = '请求超时，系统响应时间超出预期，请重试。';
      } else if (error.message?.includes('Network Error') || !error.response) {
        errorMessage = '网络错误，请检查连接后重试。';
      } else if (error.response?.status === 500) {
        errorMessage = '服务器错误，请重试；如果问题持续存在，请联系支持人员。';
      } else {
        errorMessage = '消息发送失败，请稍后重试。';
      }
      
      setSnackbar({
        open: true,
        message: errorMessage,
        severity: 'error',
      });
    },
    onSettled: () => {
      setIsLoading(false);
    },
  });

  const simulateStreamingResponse = (response: ChatUiResponse) => {
    const approvalRequired = response.execution_status === 'approval_required';
    const pendingApprovals = response.pending_approvals || [];
    // Add the message immediately so user sees response right away
    const assistantMessage: Message = {
      id: Date.now().toString(),
      type: approvalRequired
        ? 'proposed_action'
        : response.clarifying
          ? 'clarifying_question'
          : 'answer',
      content: approvalRequired ? '操作已暂停，等待经理审批。' : response.reply || '未收到响应',
      sender: 'assistant',
      timestamp: new Date(),
      route: response.route,
      run_id: response.run_id,
      confidence: response.confidence,
      structured_data: response.structured_data,
      proposals: approvalRequired ? pendingApprovals : undefined,
      execution_status: response.execution_status,
      clarifying: response.clarifying,
      evidence: response.evidence,
      reasoning_chain: response.reasoning_chain,
      reasoning_steps: response.reasoning_steps,
    };

    setMessages(prev => [...prev, assistantMessage]);

    if (approvalRequired) {
      setCurrentToolTimeline(prev => [
        ...prev,
        ...pendingApprovals.map(approval => ({
          id: approval.approval_id,
          approval_id: approval.approval_id,
          audit_id: approval.approval_id,
          action: approval.action,
          status: approval.status,
          timestamp: new Date(approval.created_at),
        })),
      ]);
      setStreamingEvents([]);
      return;
    }

    // Simulate streaming events for UI enhancement (optional)
    const events: StreamingEvent[] = [
      { stage: 'route_decision', agent: response.route || 'operations', confidence: response.confidence || 0.87 },
      { stage: 'retrieval_debug', k: 12, reranked: 6, evidence_score: 0.82 },
      { stage: 'sql_trace', query: 'SELECT * FROM orders WHERE id IN (1001,1002)', lat_ms: 38 },
    ];

    if (response.clarifying) {
      events.push({
        stage: 'clarifying_question',
        text: response.clarifying.text,
        options: response.clarifying.options,
      });
    }

    events.push({ stage: 'final_answer', text: response.reply || '暂无回答' });

    // Simulate streaming (non-blocking, just for UI enhancement)
    let eventIndex = 0;
    if (streamIntervalRef.current) {
      clearInterval(streamIntervalRef.current);
    }

    streamIntervalRef.current = setInterval(() => {
      if (eventIndex < events.length) {
        setStreamingEvents(prev => [...prev, events[eventIndex]]);
        eventIndex++;
      } else {
        if (streamIntervalRef.current) {
          clearInterval(streamIntervalRef.current);
          streamIntervalRef.current = null;
        }
        
        // Process evidence data properly
        const evidenceData = [];
        
        // Add SQL evidence if available
        if (response.evidence && Array.isArray(response.evidence)) {
          evidenceData.push(...response.evidence);
        }
        
        // Add structured data as evidence if available
        // Check both response.structured_data and context.structured_response
        const structuredData = response.structured_data || response.context?.structured_response;
        
        if (structuredData) {
          evidenceData.push({
            type: 'structured',
            id: 'structured_data',
            content: structuredData.natural_language || '结构化响应数据',
            score: structuredData.confidence || 0,
            data: structuredData
          });
          
          // Also add individual procedures as separate evidence items
          if (structuredData.data && structuredData.data.procedures && structuredData.data.procedures.procedures) {
            structuredData.data.procedures.procedures.forEach((procedure: any, index: number) => {
              evidenceData.push({
                type: 'procedure',
                id: `procedure_${procedure.id}`,
                content: procedure.description || procedure.name,
                score: 0.9, // High confidence for procedures
                data: procedure
              });
            });
          }
        }
        
        
        setCurrentEvidence(evidenceData);
        setCurrentSqlQuery(response.sql_query);
        setCurrentPlannerDecision(response.planner_decision);
        setCurrentActiveContext(response.context || {});
        setCurrentToolTimeline(response.tool_timeline || []);
        setStreamingEvents([]);
      }
    }, 500);
  };

  const handleNewConversation = () => {
    const nextSessionId = rotateChatSessionId();
    sessionIdRef.current = nextSessionId;
    setSessionId(nextSessionId);

    if (streamIntervalRef.current) {
      clearInterval(streamIntervalRef.current);
      streamIntervalRef.current = null;
    }

    setMessages([createWelcomeMessage()]);
    setInputValue('');
    setStreamingEvents([]);
    setCurrentEvidence([]);
    setCurrentSqlQuery(null);
    setCurrentPlannerDecision(null);
    setCurrentActiveContext(null);
    setCurrentToolTimeline([]);
    setCurrentReasoningChain(undefined);
    setCurrentReasoningSteps(undefined);
    setSnackbar({
      open: true,
      message: '已创建新会话。',
      severity: 'success',
    });
  };

  const handleSendMessage = async () => {
    if (!inputValue.trim() || isLoading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      type: 'answer',
      content: inputValue,
      sender: 'user',
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, userMessage]);
    setInputValue('');
    setIsLoading(true);

    try {
      await chatMutation.mutateAsync({
        message: inputValue,
        session_id: sessionId,
        context: {
          warehouse,
          // Scenario role only; API authorization is derived from the bearer token.
          role: businessRole,
          environment,
        },
        enable_reasoning: enableReasoning,
        reasoning_types: enableReasoning && selectedReasoningTypes.length > 0 ? selectedReasoningTypes : undefined,
      });
    } catch (error: any) {
      console.error('Error sending message:', error);
    }
  };
  
  const handleReasoningTypeToggle = (type: string) => {
    setSelectedReasoningTypes(prev => {
      if (prev.includes(type)) {
        return prev.filter(t => t !== type);
      } else {
        return [...prev, type];
      }
    });
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event && event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      handleSendMessage();
    }
  };

  const handleScenarioSelect = (scenario: string) => {
    const scenarioMessages: { [key: string]: string } = {
      create_pick_wave: '为 A 区订单 1001-1010 创建拣货波次，并调度一辆叉车。',
      dispatch_forklift: '调度叉车 FL-07 前往 A 区执行拣货作业。',
      log_incident: 'D2 装卸口发生机器温度过高事件。',
      check_assets: '显示所有叉车的状态和可用性。',
      safety_check: '叉车作业需要遵循哪些安全程序？',
      // Demo flow scenarios
      work_order_flow: '为 A 区订单 1001-1010 创建拣货波次，并调度一辆叉车。',
      equipment_status_flow: '显示所有叉车的状态和可用性。',
      safety_incident_flow: 'D2 装卸口发生机器温度过高事件。',
    };

    const message = scenarioMessages[scenario];
    if (message) {
      setInputValue(message);
      inputRef.current?.focus();
    }
  };

  const getStreamingStageLabel = (stage?: string) => {
    const labels: Record<string, string> = {
      route_decision: '路由决策',
      retrieval_debug: '检索调试',
      sql_trace: 'SQL 跟踪',
      proposed_action: '建议操作',
      clarifying_question: '澄清问题',
      final_answer: '最终回答',
      unknown: '未知阶段',
    };
    return labels[stage || 'unknown'] || stage;
  };

  const getAgentLabel = (agent?: string) => {
    const labels: Record<string, string> = {
      equipment: '设备智能体',
      operations: '运营智能体',
      safety: '安全智能体',
      general: '通用助手',
    };
    return agent ? (labels[agent] || agent) : '';
  };

  const applyApprovalDecision = (decisionResponse: ApprovalDecisionResponse) => {
    const { approval, workflow } = decisionResponse;
    const pendingApprovals = workflow?.pending_approvals || [];
    const approvalUpdates = new Map<string, PendingApproval>();
    [approval, ...pendingApprovals].forEach(item => {
      approvalUpdates.set(item.approval_id, item);
    });

    setMessages(prev => {
      const updatedMessages: Message[] = prev.map(message => {
        if (!message.proposals) return message;
        return {
          ...message,
          proposals: message.proposals.map(proposal =>
            approvalUpdates.get(proposal.approval_id) || proposal,
          ),
        };
      });

      const knownApprovalIds = new Set<string>();
      updatedMessages.forEach(message => {
        message.proposals?.forEach(proposal => knownApprovalIds.add(proposal.approval_id));
      });
      const newPendingApprovals = pendingApprovals.filter(
        pending => !knownApprovalIds.has(pending.approval_id),
      );

      if (workflow?.execution_status === 'approval_required' && newPendingApprovals.length > 0) {
        updatedMessages.push({
          id: `approval-${newPendingApprovals.map(item => item.approval_id).join('-')}`,
          type: 'proposed_action',
          content: '操作已暂停，等待经理审批。',
          sender: 'assistant',
          timestamp: new Date(),
          route: workflow.route || 'approval',
          run_id: newPendingApprovals[0]?.run_id,
          proposals: newPendingApprovals,
          execution_status: workflow.execution_status,
        });
      } else if (workflow?.execution_status === 'completed' && workflow.response) {
        updatedMessages.push({
          id: `approval-result-${approval.approval_id}-${Date.now()}`,
          type: 'answer',
          content: workflow.response,
          sender: 'assistant',
          timestamp: new Date(),
          route: workflow.route,
          run_id: approval.run_id,
          confidence: workflow.confidence,
          structured_data: workflow.structured_data,
          reasoning_chain: workflow.reasoning_chain,
          reasoning_steps: workflow.reasoning_steps,
          execution_status: workflow.execution_status,
        });
      }

      return updatedMessages;
    });

    setCurrentToolTimeline(prev => {
      const timelineEntry = {
        id: approval.approval_id,
        approval_id: approval.approval_id,
        audit_id: approval.approval_id,
        action: approval.action,
        status: approval.status,
        timestamp: new Date(approval.decided_at || approval.created_at),
        result: approval.result,
      };
      const existingIndex = prev.findIndex(
        item => item.approval_id === approval.approval_id || item.audit_id === approval.approval_id,
      );
      if (existingIndex === -1) return [...prev, timelineEntry];
      return prev.map((item, index) => index === existingIndex ? { ...item, ...timelineEntry } : item);
    });

    if (workflow?.context) setCurrentActiveContext(workflow.context);
    if (workflow?.reasoning_chain) setCurrentReasoningChain(workflow.reasoning_chain);
    if (workflow?.reasoning_steps) setCurrentReasoningSteps(workflow.reasoning_steps);
  };

  const handleApprovalDecision = async (
    approvalId: string,
    decision: 'approve' | 'reject',
    action: string,
  ) => {
    if (busyApprovalIdsRef.current.has(approvalId)) return;

    busyApprovalIdsRef.current.add(approvalId);
    setBusyApprovalIds(new Set(busyApprovalIdsRef.current));
    try {
      const response = await approvalAPI.decide(approvalId, decision);
      applyApprovalDecision(response);
      void queryClient.invalidateQueries({ queryKey: ['pending-approvals'] });
      setSnackbar({
        open: true,
        message: `操作 ${response.approval.action || action}：${getApprovalStatusLabel(response.approval.status)}`,
        severity: response.approval.status === 'failed' ? 'error' : 'info',
      });
    } catch (error: any) {
      setSnackbar({
        open: true,
        message: getApprovalErrorMessage(error),
        severity: 'error',
      });
    } finally {
      busyApprovalIdsRef.current.delete(approvalId);
      setBusyApprovalIds(new Set(busyApprovalIdsRef.current));
    }
  };

  const handleActionApprove = (approvalId: string, action: string) =>
    handleApprovalDecision(approvalId, 'approve', action);

  const handleActionReject = (approvalId: string, action: string) =>
    handleApprovalDecision(approvalId, 'reject', action);

  const handleQuickReply = (option: string) => {
    setInputValue(option);
    inputRef.current?.focus();
  };


  if (!isAuthenticated) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <Typography variant="h6" sx={{ color: '#ffffff' }}>
          请登录后访问聊天界面。
        </Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ height: '100vh', display: 'flex', flexDirection: 'column', backgroundColor: 'background.default' }}>
      {/* Top Bar */}
      <TopBar
        warehouse={warehouse}
        role={businessRole}
        environment={environment}
        connections={connections}
        onWarehouseChange={setWarehouse}
        onRoleChange={setBusinessRole}
        onEnvironmentChange={setEnvironment}
      />

      {/* Main Content */}
      <Box sx={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* Left Rail */}
        <LeftRail
          onScenarioSelect={handleScenarioSelect}
          onNewConversation={handleNewConversation}
          recentTasks={recentTasks}
          approvalQueue={canApprove ? (
            <ApprovalQueue
              enabled={canApprove}
              busyApprovalIds={busyApprovalIds}
              onDecision={handleApprovalDecision}
            />
          ) : undefined}
        />

        {/* Chat Area */}
        <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', backgroundColor: 'background.default' }}>
          {/* Chat Messages */}
          <Box
            sx={{
              flex: 1,
              overflow: 'auto',
              p: 0,
              backgroundColor: 'background.default',
            }}
          >
            {messages.map((message) => (
              <MessageBubble
                key={message.id}
                message={message}
                canApprove={canApprove}
                busyApprovalIds={busyApprovalIds}
                onActionApprove={handleActionApprove}
                onActionReject={handleActionReject}
                onQuickReply={handleQuickReply}
              />
            ))}

            {/* Streaming Events */}
            {streamingEvents.length > 0 && (
              <Box sx={{ px: 2, mb: 2 }}>
                <Paper sx={{ backgroundColor: 'background.paper', p: 2, border: '1px solid', borderColor: 'divider', boxShadow: 1 }}>
                  <Typography variant="body2" sx={{ color: 'primary.main', mb: 1, fontWeight: 500 }}>
                    正在处理...
                  </Typography>
                  {streamingEvents
                    .filter((event): event is StreamingEvent => event !== null && event !== undefined)
                    .map((event, index) => (
                      <Box key={index} sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                        <Typography variant="caption" sx={{ color: 'text.secondary', minWidth: '100px' }}>
                          {getStreamingStageLabel(event?.stage)}：
                        </Typography>
                        <Typography variant="caption" sx={{ color: 'text.primary' }}>
                          {event?.agent && `智能体：${getAgentLabel(event.agent)}`}
                          {event?.confidence && ` (${(event.confidence * 100).toFixed(1)}%)`}
                          {event?.k !== undefined && ` K=${event.k}→${event.reranked}`}
                          {event?.lat_ms !== undefined && ` (${event.lat_ms}ms)`}
                          {event?.action && ` ${event.action}`}
                          {event?.text && ` ${event.text}`}
                        </Typography>
                      </Box>
                    ))}
                </Paper>
              </Box>
            )}

            {/* Loading Skeleton */}
            {isLoading && (
              <Box sx={{ px: 2, mb: 2 }}>
                <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-start' }}>
                  <Skeleton variant="circular" width={32} height={32} sx={{ backgroundColor: 'grey.700' }} />
                  <Box sx={{ flex: 1 }}>
                    <Skeleton variant="rectangular" width="70%" height={60} sx={{ backgroundColor: 'background.paper', borderRadius: 2, boxShadow: 1 }} />
                  </Box>
                </Box>
              </Box>
            )}

            <div ref={messagesEndRef} />
          </Box>

          {/* Input Area */}
          <Box
            sx={{
              p: 2,
              borderTop: '1px solid',
              borderColor: 'divider',
              backgroundColor: 'background.paper',
              boxShadow: '0 -2px 8px rgba(0,0,0,0.3)',
            }}
          >
            {/* Reasoning Controls */}
            <Box sx={{ mb: 1, display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap' }}>
              <FormControlLabel
                control={
                  <Switch
                    checked={enableReasoning}
                    onChange={(e) => {
                      setEnableReasoning(e.target.checked);
                      if (!e.target.checked) {
                        setSelectedReasoningTypes([]);
                        setShowReasoningTypes(false);
                      }
                    }}
                    sx={{
                      '& .MuiSwitch-switchBase.Mui-checked': {
                        color: '#76B900',
                      },
                      '& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track': {
                        backgroundColor: '#76B900',
                      },
                    }}
                  />
                }
                label={
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                    <PsychologyIcon sx={{ fontSize: 18, color: enableReasoning ? '#76B900' : '#666666' }} />
                    <Typography variant="body2" sx={{ color: 'text.primary' }}>
                      启用推理
                    </Typography>
                  </Box>
                }
              />
              
              {enableReasoning && (
                <>
                  <Tooltip title="选择特定推理类型（留空将自动选择）">
                    <IconButton
                      size="small"
                      onClick={() => setShowReasoningTypes(!showReasoningTypes)}
                      sx={{
                        color: '#76B900',
                        '&:hover': { backgroundColor: 'rgba(118, 185, 0, 0.1)' },
                      }}
                    >
                      {showReasoningTypes ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                    </IconButton>
                  </Tooltip>
                  
                  {selectedReasoningTypes.length > 0 && (
                    <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
                      {selectedReasoningTypes.map((type) => {
                        const typeInfo = availableReasoningTypes.find(t => t.value === type);
                        return (
                          <Chip
                            key={type}
                            label={typeInfo?.label || type}
                            size="small"
                            onDelete={() => handleReasoningTypeToggle(type)}
                            sx={{
                              backgroundColor: 'primary.main',
                              color: 'primary.contrastText',
                              fontSize: '10px',
                              '& .MuiChip-deleteIcon': {
                                color: 'primary.contrastText',
                              },
                            }}
                          />
                        );
                      })}
                    </Box>
                  )}
                </>
              )}
            </Box>
            
            {/* Reasoning Type Selection */}
            <Collapse in={showReasoningTypes && enableReasoning}>
              <Paper
                sx={{
                  p: 1.5,
                  mb: 1,
                  backgroundColor: 'background.paper',
                  border: '1px solid',
                  borderColor: 'divider',
                  boxShadow: 1,
                }}
              >
                <Typography variant="caption" sx={{ color: 'text.secondary', mb: 1, display: 'block' }}>
                  选择推理类型（可选，留空将自动选择）：
                </Typography>
                <FormGroup>
                  {availableReasoningTypes.map((type) => (
                    <FormControlLabel
                      key={type.value}
                      control={
                        <Checkbox
                          checked={selectedReasoningTypes.includes(type.value)}
                          onChange={() => handleReasoningTypeToggle(type.value)}
                          sx={{
                            color: '#76B900',
                            '&.Mui-checked': {
                              color: '#76B900',
                            },
                          }}
                        />
                      }
                      label={
                        <Box>
                          <Typography variant="body2" sx={{ color: '#333333' }}>
                            {type.label}
                          </Typography>
                          <Typography variant="caption" sx={{ color: '#666666' }}>
                            {type.description}
                          </Typography>
                        </Box>
                      }
                    />
                  ))}
                </FormGroup>
              </Paper>
            </Collapse>
            
            <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-end' }}>
              <TextField
                ref={inputRef}
                fullWidth
                multiline
                maxRows={4}
                value={inputValue}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setInputValue(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="您可以询问任何仓库运营相关问题..."
                disabled={isLoading}
                sx={{
                  '& .MuiOutlinedInput-root': {
                    backgroundColor: 'background.default',
                    color: 'text.primary',
                    '& fieldset': {
                      borderColor: 'divider',
                    },
                    '&:hover fieldset': {
                      borderColor: 'primary.main',
                    },
                    '&.Mui-focused fieldset': {
                      borderColor: 'primary.main',
                    },
                  },
                  '& .MuiInputBase-input': {
                    color: 'text.primary',
                    '&::placeholder': {
                      color: 'text.secondary',
                      opacity: 1,
                    },
                  },
                }}
              />
              <IconButton
                aria-label="发送消息"
                onClick={handleSendMessage}
                disabled={!inputValue.trim() || isLoading}
                sx={{
                  backgroundColor: 'primary.main',
                  color: 'primary.contrastText',
                  '&:hover': {
                    backgroundColor: 'primary.light',
                  },
                  '&:disabled': {
                    backgroundColor: 'grey.700',
                    color: 'text.disabled',
                  },
                }}
              >
                <SendIcon />
              </IconButton>
            </Box>
          </Box>
        </Box>

        {/* Right Panel */}
        <RightPanel
          isOpen={rightPanelOpen}
          onClose={() => setRightPanelOpen(false)}
          evidence={currentEvidence}
          sqlQuery={currentSqlQuery}
          plannerDecision={currentPlannerDecision}
          activeContext={currentActiveContext}
          toolTimeline={currentToolTimeline}
          reasoningChain={currentReasoningChain}
          reasoningSteps={currentReasoningSteps}
        />
      </Box>

      {/* Floating Action Buttons */}
      <Box sx={{ position: 'fixed', bottom: 20, right: 20, display: 'flex', flexDirection: 'column', gap: 1 }}>
        <Tooltip title={rightPanelOpen ? '关闭证据与上下文面板' : '打开证据与上下文面板'} placement="left">
          <Fab
            aria-label={rightPanelOpen ? '关闭证据与上下文面板' : '打开证据与上下文面板'}
            size="small"
            onClick={() => setRightPanelOpen(!rightPanelOpen)}
            sx={{
              backgroundColor: rightPanelOpen ? 'primary.main' : 'background.paper',
              color: rightPanelOpen ? 'primary.contrastText' : 'text.primary',
              boxShadow: 2,
              '&:hover': {
                backgroundColor: rightPanelOpen ? 'primary.light' : 'background.default',
              },
            }}
          >
            {rightPanelOpen ? <CloseIcon /> : <MenuIcon />}
          </Fab>
        </Tooltip>
        
        <Tooltip title={showInternals ? '隐藏内部信息' : '显示内部信息'} placement="left">
          <Fab
            aria-label={showInternals ? '隐藏内部信息' : '显示内部信息'}
            size="small"
            onClick={() => setShowInternals(!showInternals)}
            sx={{
              backgroundColor: showInternals ? 'secondary.main' : 'background.paper',
              color: showInternals ? 'secondary.contrastText' : 'text.primary',
              boxShadow: 2,
              '&:hover': {
                backgroundColor: showInternals ? 'secondary.light' : 'background.default',
              },
            }}
          >
            {showInternals ? <VisibilityOffIcon /> : <VisibilityIcon />}
          </Fab>
        </Tooltip>
        
      </Box>

      {/* Snackbar */}
      <Snackbar
        open={snackbar.open}
        autoHideDuration={4000}
        onClose={(_, reason?: string) => {
          if (reason !== 'clickaway') {
            setSnackbar(prev => ({ ...prev, open: false }));
          }
        }}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
      >
        <Alert
          onClose={() => {
            setSnackbar(prev => ({ ...prev, open: false }));
          }}
          severity={snackbar.severity}
          sx={{ width: '100%' }}
        >
          {snackbar.message}
        </Alert>
      </Snackbar>
    </Box>
  );
};

export default ChatInterfaceNew;

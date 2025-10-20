using System;
using System.Collections.Generic;
using System.Linq;
using System.Net;
using System.Net.Sockets;
using System.Threading;
using System.Threading.Tasks;
using System.Collections.Concurrent;

namespace Clairvoyance.My_class
{
    /// <summary>
    /// UDP 高速接收（對應 TTC_Link_TCP 的等價 UDP 版本）
    /// 固定幀長 14 Bytes：0xAA | ch0..ch3(8B) | adcV(2B) | chV(2B) | 0xBB
    /// </summary>
    public class TTC_Link_UDP
    {
        #region 參數宣告

        #region 刀把連線相關參數
        private readonly string K_IP;   // 若指定 -> 僅接受該來源 IP 的 UDP；若空則接受所有來源
        private readonly int K_Port;    // 預設 4321
        private readonly int K_Count;   // 14
        private readonly int K_Ch;      // (K_Count - 2) / 2 = 6

        private Socket UDPLInk;         // UDP Socket

        #endregion

        #region 執行續規劃與內存管理參數
        private Task Tk_read;           // UDP 讀取執行續
        private Task Tk_treat;          // 解析執行續
        private CancellationTokenSource CTS_stopToken;

        // 收包先進先出佇列（與 TCP 版相同結構）
        private BlockingCollection<byte[]> FIFO_BufLst;

        // 解析後暫存：每幀 6 筆（ch0~ch3, adcV, chV）
        private List<double[]> AD7606_VarLstArF64;
        #endregion

        #endregion

        #region 初始化

        /// <param name="K_IP">
        /// 可選。若指定則只接受該來源 IP 的 UDP 封包；若要收任何來源，給 "" 或 null。
        /// </param>
        /// <param name="port">預設 4321</param>
        public TTC_Link_UDP(string K_IP = "", int port = 4321)
        {
            this.K_IP = K_IP?.Trim();
            this.K_Port = port;
            this.K_Count = 14;                 // AA + 12B payload + BB
            this.K_Ch = (K_Count - 2) / 2;  // 6
            Init();
        }

        private void Init()
        {
            FIFO_BufLst = new BlockingCollection<byte[]>(new ConcurrentQueue<byte[]>());
            CTS_stopToken = new CancellationTokenSource();
            AD7606_VarLstArF64 = new List<double[]>();
            Start();
        }

        /// <summary>
        /// 每次重啟都重新建立 Socket（避免 Disposed 狀態）
        /// </summary>
        private void Init_UDPLInk()
        {
            // 關閉舊的
            if (UDPLInk != null)
            {
                try { UDPLInk.Close(); } catch { }
                UDPLInk = null;
            }

            UDPLInk = new Socket(AddressFamily.InterNetwork, SocketType.Dgram, ProtocolType.Udp);

            // 允許重複綁定（在某些 OS/重啟情境有用）
            try
            {
                UDPLInk.SetSocketOption(SocketOptionLevel.Socket, SocketOptionName.ReuseAddress, true);
            }
            catch { /* 有些平台不支援可略過 */ }

            // 接收緩衝放大，避免突發堆積
            try { UDPLInk.ReceiveBufferSize = 4 * 1024 * 1024; } catch { }

            // 綁定本機所有介面：0.0.0.0:port
            UDPLInk.Bind(new IPEndPoint(IPAddress.Any, K_Port));

            // UDP 不需要 Connect；若要只收單一來源，我們在接收後以 IP 過濾
        }

        #endregion

        #region 對外控制 API

        /// <summary>
        /// 開始讀取（與 TCP 版對齊）
        /// </summary>
        public void Start()
        {
            Init_UDPLInk();
            Tk_read = Task.Run(Tk_read_ff);
            Tk_treat = Task.Run(Tk_treat_ff);
        }

        /// <summary>
        /// 優雅停止（與 TCP 版命名/語意相同）
        /// </summary>
        public async Task StopAsync()
        {
            try
            {
                CTS_stopToken.Cancel();

                if (UDPLInk != null)
                {
                    try
                    {
                        // UDP 不一定支援 Shutdown；以 Close 為主
                        try { UDPLInk.Shutdown(SocketShutdown.Both); } catch { }
                        UDPLInk.Close();
                    }
                    catch { }
                    UDPLInk = null;
                }

                var tasks = new List<Task>();
                if (Tk_read != null) tasks.Add(Tk_read);
                if (Tk_treat != null) tasks.Add(Tk_treat);

                if (tasks.Any())
                {
                    try { await Task.WhenAll(tasks).WaitAsync(TimeSpan.FromSeconds(2)); }
                    catch { /* 超時或取消可忽略 */ }
                }

                FIFO_BufLst?.CompleteAdding();
                FIFO_BufLst?.Dispose();

                CTS_stopToken?.Dispose();
                CTS_stopToken = new CancellationTokenSource();
                FIFO_BufLst = new BlockingCollection<byte[]>(new ConcurrentQueue<byte[]>());

                Console.WriteLine("🔧 UDP 連線資源已清理");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"❌ StopAsync 錯誤: {ex.Message}");
            }
        }

        /// <summary>
        /// 取出解析後資料（每呼叫會清空內部暫存），與 TCP 版一致
        /// </summary>
        public List<double>[] GetArLstF64()
        {
            if (AD7606_VarLstArF64 == null || AD7606_VarLstArF64.Count < 1)
                return null;

            List<double>[] re = new List<double>[this.K_Ch];
            for (int i = 0; i < re.Length; i++) re[i] = new List<double>();

            // 深拷貝避免競態
            var copy = AD7606_VarLstArF64.Select(arr => arr.ToArray()).ToList();

            foreach (var arr in copy)
            {
                for (int i = 0; i < arr.Length && i < re.Length; i++)
                    re[i].Add(arr[i]);
            }

            // 清空暫存
            AD7606_VarLstArF64 = new List<double[]>();
            return re;
        }

        #endregion

        #region 內部工作執行緒

        /// <summary>
        /// UDP 接收執行緒：
        /// - ReceiveFrom() 收包
        /// - 若設定 K_IP，則僅接受該來源 IP
        /// - 封裝為 byte[] 丟進 FIFO
        /// </summary>
        private void Tk_read_ff()
        {
            var ct = CTS_stopToken.Token;

            // 預先解析過濾目標（若未指定則不過濾）
            IPAddress? filterIp = null;
            if (!string.IsNullOrWhiteSpace(K_IP) && IPAddress.TryParse(K_IP, out var ipParsed))
                filterIp = ipParsed;

            // 單一、可重複使用的接收緩衝區（避免每包 new）
            byte[] buf = new byte[8192];

            // 這個 EndPoint 物件會被內部填寫來源位址
            EndPoint remote = new IPEndPoint(IPAddress.Any, 0);

            // 同步阻塞接收以最小化排程/配置成本（在專用背景執行緒裡，不會卡 UI）
            while (!ct.IsCancellationRequested)
            {
                try
                {
                    int len = UDPLInk.ReceiveFrom(buf, 0, buf.Length, SocketFlags.None, ref remote);
                    if (len <= 0) continue;

                    // 來源 IP 位元組比對（不做 ToString()）
                    if (filterIp != null)
                    {
                        var fromIp = ((IPEndPoint)remote).Address;
                        // 若來源不等於指定 IP，直接丟棄（零配置）
                        if (!fromIp.Equals(filterIp))
                            continue;
                    }

                    // 只有匹配來源時，才配置一塊剛好長度的陣列放進 FIFO
                    byte[] data = new byte[len];
                    Buffer.BlockCopy(buf, 0, data, 0, len);
                    FIFO_BufLst.Add(data, ct);
                }
                catch (SocketException ex)
                {
                    // 常見暫時性錯誤，稍作喘息避免 busy-loop
                    System.Diagnostics.Debug.WriteLine($"UDP Receive err: {ex.SocketErrorCode}");
                    Thread.Sleep(5);
                }
                catch (ObjectDisposedException)
                {
                    break; // socket 關閉
                }
                catch (OperationCanceledException)
                {
                    break; // 要求停止
                }
                catch (Exception ex)
                {
                    System.Diagnostics.Debug.WriteLine($"UDP Receive err: {ex.Message}");
                    Thread.Sleep(5);
                }
            }
        }

        /// <summary>
        /// 解析執行緒（維持與 TCP 版同樣的對齊/尋框邏輯）
        /// </summary>
        private void Tk_treat_ff()
        {
            List<byte> rew_data = new List<byte>();
            int processed_index = 0;
            int data_long = K_Count - 2;           // 12
            const int MAX_BUFFER_SIZE = 1024 * 1024;

            var ct = CTS_stopToken.Token;

            while (!ct.IsCancellationRequested)
            {
                try
                {
                    byte[] data = FIFO_BufLst.Take(ct);
                    rew_data.AddRange(data);

                    // 緩衝保護
                    if (rew_data.Count > MAX_BUFFER_SIZE)
                    {
                        if (processed_index < rew_data.Count)
                        {
                            var remaining = rew_data.GetRange(processed_index, rew_data.Count - processed_index);
                            rew_data.Clear();
                            rew_data.AddRange(remaining);
                            processed_index = 0;
                        }
                        else
                        {
                            rew_data.Clear();
                            processed_index = 0;
                        }
                    }

                    int i = processed_index;

                    // 尋找 0xAA ... 0xBB 的完整幀
                    while (i <= rew_data.Count - (data_long + 2))
                    {
                        if (rew_data[i] == 0xAA && rew_data[i + data_long + 1] == 0xBB)
                        {
                            // 扣掉頭尾，取 12 Bytes payload
                            byte[] packet = rew_data.GetRange(i + 1, data_long).ToArray();

                            try { AD7606_VarLstArF64_Add(packet); }
                            catch (Exception ex)
                            {
                                System.Diagnostics.Debug.WriteLine($"封包處理錯誤: {ex.Message}");
                            }

                            i += data_long + 2; // 跳過整幀
                        }
                        else
                        {
                            // 未對齊，往後滑動一位
                            i++;
                        }
                    }

                    processed_index = i;
                }
                catch (OperationCanceledException) { break; }
                catch (Exception ex)
                {
                    System.Diagnostics.Debug.WriteLine($"資料處理錯誤: {ex.Message}");
                    continue;
                }
            }
        }

        #endregion

        #region 資料轉換/累積

        private void AD7606_VarLstArF64_Add(byte[] packet)
        {
            // 期望 packet.Length = 12，依序：ch0..ch3, adcV, chV（每項 2B, big-endian）
            double[] dvar = new double[this.K_Ch];

            for (int ch = 0, i = 0; ch < this.K_Ch; ch++, i += 2)
            {
                ushort u16 = (ushort)((packet[i] << 8) | packet[i + 1]);
                dvar[ch] = AD7606ConvValue(u16);
            }

            AD7606_VarLstArF64.Add(dvar);
        }

        /// <summary>
        /// AD7606 16-bit 轉 ±5V（與 TCP 版一致）
        /// </summary>
        private double AD7606ConvValue(ushort bin)
        {
            short signedVal = (short)bin;      // 2 補數
            return (signedVal * 5.0) / 32768.0;
        }

        #endregion
    }
}

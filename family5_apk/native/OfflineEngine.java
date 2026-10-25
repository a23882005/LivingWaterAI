package tw.livingwater.family5;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import org.json.JSONObject;
import org.json.JSONArray;
import java.io.File;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.security.MessageDigest;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;
import android.util.Base64;
import android.content.ContentValues;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;

public final class OfflineEngine {
    private static String now() {
        SimpleDateFormat f=new SimpleDateFormat("yyyy-MM-dd HH:mm:ss",Locale.TAIWAN);
        f.setTimeZone(TimeZone.getTimeZone("Asia/Taipei")); return f.format(new Date());
    }
    private static void schema(SQLiteDatabase db) {
        db.execSQL("CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT NOT NULL)");
        db.execSQL("CREATE TABLE IF NOT EXISTS positions (symbol TEXT PRIMARY KEY, qty TEXT NOT NULL, cost_basis TEXT NOT NULL, currency TEXT NOT NULL)");
        db.execSQL("CREATE TABLE IF NOT EXISTS targets (symbol TEXT PRIMARY KEY, target_pct TEXT NOT NULL)");
        db.execSQL("CREATE TABLE IF NOT EXISTS candidates (symbol TEXT PRIMARY KEY, note TEXT NOT NULL, at TEXT NOT NULL)");
        db.execSQL("CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, kind TEXT NOT NULL, symbol TEXT NOT NULL, qty TEXT NOT NULL, price TEXT NOT NULL, amount TEXT NOT NULL, currency TEXT NOT NULL, note TEXT NOT NULL)");
        db.execSQL("CREATE TABLE IF NOT EXISTS reports (id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, html TEXT NOT NULL)");
    }
    private static String single(SQLiteDatabase db,String sql,String[] args,String fallback){
        try(Cursor c=db.rawQuery(sql,args)){return c.moveToFirst()?c.getString(0):fallback;}
    }
    private static String meta(SQLiteDatabase db,String key,String defaultValue) {
        return single(db,"SELECT v FROM meta WHERE k=?",new String[]{key},defaultValue);
    }
    private static void setMeta(SQLiteDatabase db,String key,String value){
        ContentValues v=new ContentValues();v.put("k",key);v.put("v",value);
        db.insertWithOnConflict("meta",null,v,SQLiteDatabase.CONFLICT_REPLACE);
    }
    private static String hash(String pin,String salt) throws Exception{
        byte[] s=Base64.decode(salt,Base64.NO_WRAP);
        PBEKeySpec spec=new PBEKeySpec(pin.toCharArray(),s,120000,256);
        try {return Base64.encodeToString(SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256").generateSecret(spec).getEncoded(),Base64.NO_WRAP);}
        finally {spec.clearPassword();}
    }
    private static void checkPin(String pin) {
        if(pin.length()<4||pin.length()>64)throw new IllegalArgumentException("密碼需為4～64字元");
    }
    private static boolean matches(SQLiteDatabase db,String pin)throws Exception{
        String stored=meta(db,"pin_hash","");
        return !stored.isEmpty()&&MessageDigest.isEqual(hash(pin,meta(db,"pin_salt","")).getBytes(StandardCharsets.UTF_8),stored.getBytes(StandardCharsets.UTF_8));
    }
    private static BigDecimal money(String x,String label,boolean zeroOk){
        try{
            BigDecimal n=new BigDecimal(x.trim());
            if(n.signum()<0 || (!zeroOk&&n.signum()==0) || n.precision()>20)throw new Exception();
            return n;
        }catch(Exception ex){throw new IllegalArgumentException(label+"需要有效正數");}
    }
    private static String decimal(BigDecimal d){return d.stripTrailingZeros().toPlainString();}
    private static String id(String s){
        String v=s==null?"":s.trim().toUpperCase(Locale.US);
        if(!v.matches("[A-Z0-9][A-Z0-9._-]{0,19}"))throw new IllegalArgumentException("標的代號格式不正確");
        return v;
    }
    private static String currency(String s){
        String v=s==null?"USD":s.trim().toUpperCase(Locale.US);
        if(!v.matches("USD|TWD|EUR|GBP|JPY"))throw new IllegalArgumentException("幣別須為USD/TWD/EUR/GBP/JPY");
        return v;
    }
    private static String txt(JSONObject p,String k,String def){return p.optString(k,def);}
    private static String safe(String s){return s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace("\"","&quot;").replace("'","&#39;");}
    private static JSONObject result(String text)throws Exception{return new JSONObject().put("ok",true).put("text",text);}
    private static String positions(SQLiteDatabase db){
        StringBuilder b=new StringBuilder("我的本機持倉（歷史成本，非即時市值）\n");
        try(Cursor c=db.rawQuery("SELECT symbol,qty,cost_basis,currency FROM positions ORDER BY symbol",null)){
            if(!c.moveToFirst())return "目前尚無持倉，請使用01建立。";
            do{b.append(c.getString(0)).append("｜").append(c.getString(1)).append(" 股｜成本 ")
                .append(c.getString(2)).append(" ").append(c.getString(3)).append("\n");}while(c.moveToNext());
        }
        b.append("\n資料儲存於這台裝置，沒有即時行情。");return b.toString();
    }
    private static String targets(SQLiteDatabase db){
        StringBuilder b=new StringBuilder("本機目標比例\n");
        BigDecimal total=BigDecimal.ZERO;
        try(Cursor c=db.rawQuery("SELECT symbol,target_pct FROM targets ORDER BY symbol",null)){
            while(c.moveToNext()){b.append(c.getString(0)).append("｜").append(c.getString(1)).append("%\n");
                total=total.add(new BigDecimal(c.getString(1)));}}
        return b.append("合計 ").append(decimal(total)).append("%；尚未指定 ").append(decimal(new BigDecimal(100).subtract(total))).append("%").toString();
    }
    private static String events(SQLiteDatabase db){
        StringBuilder b=new StringBuilder();
        try(Cursor c=db.rawQuery("SELECT at,kind,symbol,qty,price,amount,currency,note FROM events ORDER BY id DESC LIMIT 30",null)){
            while(c.moveToNext())b.append(c.getString(0)).append(" ").append(c.getString(1)).append(" ")
                 .append(c.getString(2)).append(" 數量").append(c.getString(3)).append(" 金額")
                 .append(c.getString(5)).append(" ").append(c.getString(6)).append(" ").append(c.getString(7)).append("\n");}
        return b.length()==0?"尚無交易或資金紀錄":b.toString();
    }
    private static String record(SQLiteDatabase db,String kind,String sym,String qty,String price,String amount,String curr,String note){
        curr=currency(curr);
        if(!kind.matches("buy|sell|dividend|deposit|withdrawal"))throw new IllegalArgumentException("無效交易類別");
        if(note.length()>500)throw new IllegalArgumentException("備註最多500字");
        BigDecimal q=BigDecimal.ZERO,p=BigDecimal.ZERO,amt=BigDecimal.ZERO;
        if(kind.equals("buy")||kind.equals("sell")){
            sym=id(sym);q=money(qty,"股數",false);p=money(price,"成交價格",false);amt=q.multiply(p);
            try(Cursor c=db.rawQuery("SELECT qty,cost_basis,currency FROM positions WHERE symbol=?",new String[]{sym})){
                boolean exists=c.moveToFirst();
                BigDecimal oldq=exists?new BigDecimal(c.getString(0)):BigDecimal.ZERO;
                BigDecimal oldcost=exists?new BigDecimal(c.getString(1)):BigDecimal.ZERO;
                if(exists&&!c.getString(2).equals(curr))throw new IllegalArgumentException("此標的幣別與既有持倉不同");
                if(kind.equals("sell")&&oldq.compareTo(q)<0)throw new IllegalArgumentException("賣出股數超過持倉");
                BigDecimal nq=kind.equals("buy")?oldq.add(q):oldq.subtract(q);
                BigDecimal nc=kind.equals("buy")?oldcost.add(amt):(nq.signum()==0?BigDecimal.ZERO:oldcost.multiply(nq).divide(oldq,10,java.math.RoundingMode.HALF_UP));
                if(nq.signum()==0)db.delete("positions","symbol=?",new String[]{sym});
                else {ContentValues cv=new ContentValues();cv.put("symbol",sym);cv.put("qty",decimal(nq));cv.put("cost_basis",decimal(nc));cv.put("currency",curr);
                    db.insertWithOnConflict("positions",null,cv,SQLiteDatabase.CONFLICT_REPLACE);}
            }
        }else{
            if(kind.equals("dividend"))sym=id(sym);else sym="";
            amt=money(amount,"金額",false);
        }
        ContentValues cv=new ContentValues();cv.put("at",now());cv.put("kind",kind);cv.put("symbol",sym);
        cv.put("qty",decimal(q));cv.put("price",decimal(p));cv.put("amount",decimal(amt));cv.put("currency",curr);cv.put("note",note);
        db.insertOrThrow("events",null,cv);
        return "已記錄："+kind+" "+sym+"，金額 "+decimal(amt)+" "+curr+
           ((kind.equals("buy")||kind.equals("sell"))?"\n\n"+positions(db):"");
    }
    private static String exposure(SQLiteDatabase db){
        String[] currencies={null};BigDecimal sum=BigDecimal.ZERO;
        try(Cursor c=db.rawQuery("SELECT cost_basis,currency FROM positions",null)){
            while(c.moveToNext()){
                String cur=c.getString(1);
                if(currencies[0]!=null&&!currencies[0].equals(cur))return "存在多種幣別；未取得可靠匯率，暫無法跨幣別比較。\n正式投資建議須接入W5/V82引擎。";
                currencies[0]=cur;sum=sum.add(new BigDecimal(c.getString(0)));
            }
        }
        if(sum.signum()==0)return "尚未建立持倉，請先使用01。";
        StringBuilder b=new StringBuilder("成本占比參考（非現價市值）\n");
        try(Cursor c=db.rawQuery("SELECT p.symbol,p.cost_basis,t.target_pct FROM positions p LEFT JOIN targets t ON p.symbol=t.symbol ORDER BY p.symbol",null)){
            while(c.moveToNext()){
                BigDecimal pct=new BigDecimal(c.getString(1)).multiply(new BigDecimal(100)).divide(sum,2,java.math.RoundingMode.HALF_UP);
                b.append(c.getString(0)).append("｜成本占比 ").append(pct).append("%｜目標 ")
                  .append(c.isNull(2)?"未設定":c.getString(2)+"%").append("\n");
            }
        }
        return b.append("\n此為本機成本摘要，並非正式V82買賣建議。").toString();
    }
    private static String table(SQLiteDatabase db,String sql,String[] cols){
        StringBuilder b=new StringBuilder("<table><thead><tr>");
        for(String col:cols)b.append("<th>").append(safe(col)).append("</th>");
        b.append("</tr></thead><tbody>");
        try(Cursor c=db.rawQuery(sql,null)){
            while(c.moveToNext()){b.append("<tr>");
                for(int i=0;i<cols.length;i++)b.append("<td>").append(safe(c.getString(i))).append("</td>");
                b.append("</tr>");}
        }
        return b.append("</tbody></table>").toString();
    }
    private static String html(SQLiteDatabase db) {
        return "<!doctype html><html lang='zh-Hant'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"+
          "<style>body{font-family:sans-serif;padding:20px;color:#243c33}h1{color:#27704e}table{width:100%;border-collapse:collapse}th,td{padding:8px;border:1px solid #aaa;word-break:break-word}th{background:#edf5ed}p{line-height:1.6}</style>"+
          "<h1>第五位家人｜本機配置摘要</h1><p>製作時間："+safe(now())+"</p><p>本機歷史成本，不含即時市值、外部資料或正式V82建議。</p>"+
          "<h2>持倉</h2>"+table(db,"SELECT symbol,qty,cost_basis,currency FROM positions ORDER BY symbol",new String[]{"代號","股數","總成本","幣別"})+
          "<h2>目標配置</h2>"+table(db,"SELECT symbol,target_pct FROM targets ORDER BY symbol",new String[]{"代號","目標%"})+
          "<h2>生活與投資需求</h2><p>"+safe(meta(db,"profile","尚無備註"))+"</p></html>";
    }
    private static JSONObject run(SQLiteDatabase db,String op,JSONObject p)throws Exception{
        if(op.equals("init"))return new JSONObject().put("ok",true).put("pin_set",!meta(db,"pin_hash","").isEmpty()).put("owner",meta(db,"owner","第五位家人"));
        if(op.equals("pin_setup")){
            if(!meta(db,"pin_hash","").isEmpty())throw new IllegalArgumentException("本機密碼已設定");
            String pin=txt(p,"pin","");checkPin(pin);byte[] salt=new byte[16];new SecureRandom().nextBytes(salt);
            String enc=Base64.encodeToString(salt,Base64.NO_WRAP);setMeta(db,"pin_salt",enc);setMeta(db,"pin_hash",hash(pin,enc));
            String owner=txt(p,"owner","第五位家人").trim();setMeta(db,"owner",owner.isEmpty()?"第五位家人":owner.substring(0,Math.min(60,owner.length())));
            return result("本機密碼設定完成");
        }
        if(op.equals("pin_login")){if(!matches(db,txt(p,"pin","")))throw new IllegalArgumentException("密碼不正確");return result("登入成功");}
        if(op.equals("pin_change")){
            if(!matches(db,txt(p,"old","")))throw new IllegalArgumentException("原密碼錯誤");
            String pin=txt(p,"new","");checkPin(pin);byte[] salt=new byte[16];new SecureRandom().nextBytes(salt);
            String enc=Base64.encodeToString(salt,Base64.NO_WRAP);setMeta(db,"pin_salt",enc);setMeta(db,"pin_hash",hash(pin,enc));
            return result("密碼已更新");
        }
        if(meta(db,"pin_hash","").isEmpty())throw new IllegalArgumentException("請先設定密碼");
        switch(op){
            case "read_portfolio":return result(positions(db));
            case "first_allocation":return result(record(db,"buy",txt(p,"symbol",""),txt(p,"qty",""),txt(p,"price",""),"0",txt(p,"currency","USD"),"第一次建倉"));
            case "targets":return result(targets(db));
            case "adjust_target": {
                String sym=id(txt(p,"symbol",""));BigDecimal pct=money(txt(p,"pct",""),"目標比例",true);
                if(pct.compareTo(new BigDecimal(100))>0)throw new IllegalArgumentException("比例超過100%");
                BigDecimal other=BigDecimal.ZERO;
                try(Cursor c=db.rawQuery("SELECT target_pct FROM targets WHERE symbol<>?",new String[]{sym})){
                    while(c.moveToNext())other=other.add(new BigDecimal(c.getString(0)));}
                if(other.add(pct).compareTo(new BigDecimal(100))>0)throw new IllegalArgumentException("目標比例加總超過100%");
                if(pct.signum()==0)db.delete("targets","symbol=?",new String[]{sym});
                else{ContentValues v=new ContentValues();v.put("symbol",sym);v.put("target_pct",decimal(pct));db.insertWithOnConflict("targets",null,v,SQLiteDatabase.CONFLICT_REPLACE);}
                return result(targets(db));
            }
            case "research_candidates":{
                String sym=id(txt(p,"symbol",""));String note=txt(p,"note","").trim();
                if(note.isEmpty()||note.length()>500)throw new IllegalArgumentException("候選筆記需為1～500字");
                ContentValues v=new ContentValues();v.put("symbol",sym);v.put("note",note);v.put("at",now());
                db.insertWithOnConflict("candidates",null,v,SQLiteDatabase.CONFLICT_REPLACE);
                return result("已記錄候選："+sym);
            }
            case "candidates":{
                StringBuilder b=new StringBuilder();
                try(Cursor c=db.rawQuery("SELECT symbol,note FROM candidates ORDER BY at DESC",null)){
                    while(c.moveToNext())b.append(c.getString(0)).append("｜").append(c.getString(1)).append("\n");}
                return result(b.length()==0?"尚無候選記錄":b.toString());
            }
            case "deployment_pace":return result(exposure(db));
            case "new_funding":return result(record(db,"deposit","","0","0",txt(p,"amount",""),txt(p,"currency","TWD"),txt(p,"note","")));
            case "profile":return result(meta(db,"profile","尚無備註"));
            case "update_profile":{
                String note=txt(p,"note","");if(note.length()>3000)throw new IllegalArgumentException("備註最多3000字");
                setMeta(db,"profile",note);return result("已更新本機生活與投資需求");
            }
            case "record_event":return result(record(db,txt(p,"kind",""),txt(p,"symbol",""),txt(p,"qty","0"),txt(p,"price","0"),txt(p,"amount","0"),txt(p,"currency","USD"),txt(p,"note","")));
            case "events":return result(events(db));
            case "generate_report":{
                String h=html(db);ContentValues v=new ContentValues();v.put("at",now());v.put("html",h);
                db.insertOrThrow("reports",null,v);return new JSONObject().put("ok",true).put("html",h).put("text","本機歷史配置摘要");
            }
            case "previous_report":{
                String h=single(db,"SELECT html FROM reports ORDER BY id DESC LIMIT 1",null,"");
                if(h.isEmpty())return result("尚無報告，請先使用13產生");
                return new JSONObject().put("ok",true).put("html",h).put("text","上次配置摘要");
            }
            default:throw new IllegalArgumentException("未知操作："+op);
        }
    }
    public static JSONObject api(String dbPath,String operation,String payload){
        SQLiteDatabase db=null;
        try{
            File file=new File(dbPath); if(!file.getParentFile().exists()&&!file.getParentFile().mkdirs())throw new IllegalStateException("無法建立資料庫資料夾");
            db=SQLiteDatabase.openOrCreateDatabase(file,null);schema(db);
            db.beginTransaction();
            JSONObject response=run(db,operation,new JSONObject(payload));
            db.setTransactionSuccessful();return response;
        }catch(Exception e){
            try{return new JSONObject().put("ok",false).put("error",e.getMessage()==null?"資料操作錯誤":e.getMessage());}
            catch(Exception ignored){return new JSONObject();}
        }finally{
            if(db!=null){if(db.inTransaction())db.endTransaction();db.close();}
        }
    }
}
